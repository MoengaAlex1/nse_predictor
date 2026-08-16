"""
clamp_rtdb_ohlc.py

Catches per-field price errors that fix_decimal_scale.py can't see. That script
judges rows by Close alone and scales o/h/l/c together, so a row where only Low
or High is decimal-shifted (Thursday CTUM had Low=171.5 while Open/Close were
fine at 170 after row-level correction) never reaches the corrector.

Three detection strategies, in order of precedence:

  1. PER-FIELD POWER-OF-TEN
     For each of o/h/l/c independently, compare against that field's trailing
     30-day median. If the ratio is a clean 10x / 100x / 1000x — same tolerance
     as fix_decimal_scale.py — the field is decimal-shifted, and correcting it
     restores OHLC coherence.

  2. OHLC CLAMP
     A session on NSE always satisfies

         Low <= min(Open, Close) <= max(Open, Close) <= High

     so a row violating that has at least one field wrong. When Open and Close
     are themselves trustworthy, min/max of (O,C) tells us what the wrong Low
     or High should be. Same algorithm as nse_price_cleaner.py:clamp_ohlc(),
     applied directly to RTDB.

  3. REPORT
     If a field is way off but not by a clean power of ten, or if the OHLC
     violation exists but Open/Close themselves are suspect (drift too far from
     the trailing 30-day Close median for us to trust them), we log the row
     without touching it. Never guess; never fabricate.

SAFETY GUARDS
-------------
* Open and Close are never mutated by the OHLC clamp — they are the evidence,
  so modifying them here would be circular. They CAN be mutated by the
  per-field power-of-ten pass, but only when the ratio to the field's own
  median lands cleanly within the TOLERANCE around a factor.
* OHLC clamp skips rows where min(O,C) drifts more than OC_PLAUSIBILITY_MAX_DRIFT
  from the trailing 30-day Close median. That drift means O/C are themselves
  outside the level the stock is trading at, and using them as the clamp
  anchor would land Low or High on the wrong number.
* Every write is preceded by a JSON backup so any run can be replayed and
  reversed.

Read-only unless --apply is passed.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Reuse the tolerance and factor rules from fix_decimal_scale.py so both
# detectors treat "close to a clean power of ten" the same way.
from pipeline.scripts.fix_decimal_scale import scale_error, FACTORS, TOLERANCE

log = logging.getLogger(__name__)

# If Open and Close disagree by more than this share of Close, one of them is
# almost certainly wrong and min/max of (O,C) is no longer safe as an anchor.
SAFETY_SPREAD_PCT = 0.40

# Trailing-median plausibility guard for min(O,C). If Open and Close agree
# with each other but both drift more than this fraction from the trailing
# 30-day Close median, the row's own O/C evidence isn't trustworthy — clamping
# to min(O,C) would land Low or High on the wrong number.
OC_PLAUSIBILITY_MAX_DRIFT = 0.25

# Length of the trailing per-field median window. Matches the short-window
# anchor in fix_decimal_scale.py so both scripts judge "recent level" the same
# way.
TRAILING_DAYS = 30

# Minimum window rows before the trailing median is trusted as an anchor.
MIN_TRAILING_ROWS = 5

# Field is flagged as an outlier for review (not corrected) when its ratio to
# the trailing per-field median exceeds this magnitude and it's not a clean
# power of ten. BAT High = 1000 vs a trailing median around 581 (ratio 1.72)
# falls below this and is left alone; genuinely wild fields (High = 30x
# median without being a clean power of ten) get reported.
FIELD_OUTLIER_MIN_RATIO = 3.0

PRICE_FIELDS = ("o", "h", "l", "c")

# Fields that are safe to mutate under the per-field decimal-scale rule.
# Everything is safe here — a clean power-of-ten shift is a clean shift, and
# Open/Close carry no special status against their own history. The OHLC-clamp
# fallback is what treats O/C as evidence rather than data.
PER_FIELD_MUTABLE = PRICE_FIELDS


def _sorted_price_dates(node: dict) -> list[str]:
    """ISO-date strings that carry a numeric OHLC row, in chronological order."""
    return sorted(
        d for d, v in node.items()
        if isinstance(v, dict)
        and all(isinstance(v.get(f), (int, float)) and v[f] > 0 for f in PRICE_FIELDS)
    )


def _trailing_median(node: dict, dates: list[str], target: str,
                     field: str, n: int = TRAILING_DAYS) -> float | None:
    """
    Median of `field` over the `n` trading days ending just before `target`.

    Trailing-only so the anchor cannot be biased by the corrupt row itself or
    by any later row a correction will land on. Matches the recency-anchor
    approach in fix_decimal_scale.py:local_level_short().
    """
    try:
        idx = dates.index(target)
    except ValueError:
        return None
    start = max(0, idx - n)
    values = [
        node[d].get(field) for d in dates[start:idx]
    ]
    values = [v for v in values if isinstance(v, (int, float)) and v > 0]
    if len(values) < MIN_TRAILING_ROWS:
        return None
    values.sort()
    return values[len(values) // 2]


def _apply_factor(value: float, factor: int) -> float:
    """
    Invert a decimal-scale factor. Positive factor means the value is too
    large and must be divided; negative means it's too small and must be
    multiplied. Mirrors correct_row() in fix_decimal_scale.py so both scripts
    apply the sign convention the same way.
    """
    return value / factor if factor > 0 else value * (-factor)


def find_violations(node: dict) -> list[dict]:
    """
    Return a list of proposed actions on this ticker's rows.

    Each item has an `action`:
      * "per_field_fix" — one or more fields are decimal-shifted vs their own
        trailing median AND correcting them restores OHLC coherence. Safe to
        auto-apply.
      * "clamp" — OHLC violation where Open and Close look trustworthy against
        the trailing Close median. Safe to auto-apply; only l and h move.
      * "report" — evidence of a bad row but no algorithmic fix is safe.
        Logged with a reason; never written.
    """
    out: list[dict] = []
    dates = _sorted_price_dates(node)

    for date in dates:
        row = node[date]
        o, h, l, c = row["o"], row["h"], row["l"], row["c"]

        # ── Pass 1: per-field power-of-ten ───────────────────────────────────
        # Every field gets judged against its own trailing 30-day median. A
        # ratio that lands within TOLERANCE of a clean power of ten is a
        # decimal shift on THAT field alone; we know the direction from the
        # sign of the factor and the magnitude from the anchor.
        per_field_fix: dict[str, float] = {}
        per_field_reasons: list[str] = []
        for f in PRICE_FIELDS:
            anchor = _trailing_median(node, dates, date, f)
            if anchor is None:
                continue
            factor = scale_error(row[f], anchor)
            if factor is None:
                continue
            corrected = round(_apply_factor(row[f], factor), 4)
            per_field_fix[f] = corrected
            per_field_reasons.append(
                f"{f}: {row[f]}→{corrected} (median {anchor:.4f}, factor {factor:+d})"
            )

        if per_field_fix:
            # Only apply if the corrected row satisfies OHLC coherence — the
            # power-of-ten evidence per field is strong on its own, but if
            # applying it produces an incoherent row then the per-field
            # anchors probably disagree about what the row's real level is
            # and we should not guess.
            new_row = {**row, **per_field_fix}
            new_o, new_h, new_l, new_c = new_row["o"], new_row["h"], new_row["l"], new_row["c"]
            coherent = (new_l <= min(new_o, new_c) <= max(new_o, new_c) <= new_h
                        and new_l <= new_h and new_l > 0)
            if coherent:
                out.append({
                    "date": date,
                    "before": dict(row),
                    "after":  new_row,
                    "action": "per_field_fix",
                    "reason": "; ".join(per_field_reasons),
                    "fields": sorted(per_field_fix.keys()),
                })
                continue
            # Otherwise fall through — the OHLC clamp may still handle it, or
            # this row will be reported below.

        # ── Pass 2: OHLC clamp ───────────────────────────────────────────────
        # A session with Low > min(Open, Close) or High < max(Open, Close) has
        # one or more fields wrong. When Open and Close are trustworthy their
        # min/max tells us what the wrong Low/High should be. We check
        # trustworthiness two ways: (a) intra-row spread, (b) distance from
        # the trailing Close median.
        low_wrong  = l > min(o, c)
        high_wrong = h < max(o, c)
        crossed    = l > h
        if not (low_wrong or high_wrong or crossed):
            continue

        # Guard (a) — spread between Open and Close inside the row.
        if abs(o - c) > SAFETY_SPREAD_PCT * c:
            out.append({
                "date": date, "before": dict(row), "after": None,
                "action": "report",
                "reason": (f"OHLC violation but |O-C|/C={abs(o-c)/c:.2f} > "
                           f"{SAFETY_SPREAD_PCT} — O and C disagree, clamp anchor unsafe"),
                "fields": [],
            })
            continue

        # Guard (b) — do O and C agree with the trailing Close median?
        # Catches the case where Open and Close agree with each other but are
        # both wrong (BAT Thu had O=C=521 vs trailing median ~579 — the row's
        # own O/C evidence would land the Low on the wrong number).
        c_median = _trailing_median(node, dates, date, "c")
        if c_median is not None:
            oc_anchor = min(o, c)
            drift = abs(oc_anchor - c_median) / c_median
            if drift > OC_PLAUSIBILITY_MAX_DRIFT:
                out.append({
                    "date": date, "before": dict(row), "after": None,
                    "action": "report",
                    "reason": (f"OHLC violation but min(O,C)={oc_anchor:.4f} "
                               f"drifts {drift*100:.0f}% from trailing c-median "
                               f"{c_median:.4f} — O/C themselves suspect"),
                    "fields": [],
                })
                continue

        # Both guards passed — safe to derive Low and High from min/max(O,C).
        correct_low  = min(o, c)
        correct_high = max(o, c)
        new_l = correct_low  if (low_wrong  or crossed) else l
        new_h = correct_high if (high_wrong or crossed) else h
        if new_l > new_h:
            new_l, new_h = correct_low, correct_high
        if new_l == l and new_h == h:
            continue

        reasons = []
        if crossed:    reasons.append(f"L({l})>H({h})")
        if low_wrong:  reasons.append(f"L({l})>min(O,C)={correct_low}")
        if high_wrong: reasons.append(f"H({h})<max(O,C)={correct_high}")

        out.append({
            "date":   date,
            "before": dict(row),
            "after":  {**row, "l": round(new_l, 4), "h": round(new_h, 4)},
            "action": "clamp",
            "reason": "; ".join(reasons),
            "fields": [f for f, cur, new in
                       (("l", l, new_l), ("h", h, new_h)) if cur != new],
        })

    # ── Pass 3: per-field outlier report (no writes) ─────────────────────────
    # Any surviving row where a single field is more than FIELD_OUTLIER_MIN_RATIO
    # times its trailing median, and it wasn't a clean power-of-ten shift, gets
    # logged for review. Non-decimal outliers (BAT H=1000 with ratio ~1.72 vs
    # median 581 is BELOW the threshold, so this pass would skip it; KEGN H=250
    # with ratio ~24 vs median 10.5 is ABOVE and would be reported).
    handled_dates = {v["date"] for v in out}
    for date in dates:
        if date in handled_dates:
            continue
        row = node[date]
        for f in PRICE_FIELDS:
            anchor = _trailing_median(node, dates, date, f)
            if anchor is None:
                continue
            v = row[f]
            ratio = max(v / anchor, anchor / v)
            if ratio >= FIELD_OUTLIER_MIN_RATIO and scale_error(v, anchor) is None:
                out.append({
                    "date":   date,
                    "before": dict(row), "after": None,
                    "action": "report",
                    "reason": (f"{f}={v} vs trailing median {anchor:.4f} "
                               f"(ratio {ratio:.1f}x) — non-decimal outlier"),
                    "fields": [f],
                })
                break

    return out


def scan(db: dict, tickers: list[str] | None = None) -> dict[str, list[dict]]:
    found: dict[str, list[dict]] = {}
    for ticker in sorted(db):
        if tickers and ticker not in tickers:
            continue
        node = db[ticker]
        if not isinstance(node, dict):
            continue
        rows = find_violations(node)
        if rows:
            found[ticker] = rows
    return found


def dump(ticker: str, node: dict, last_n: int = 10) -> None:
    """Print the last N dated rows of a ticker for eyeball diagnosis."""
    if not isinstance(node, dict):
        log.info("%s: no data in RTDB", ticker)
        return
    dates = sorted(d for d, v in node.items() if isinstance(v, dict))[-last_n:]
    if not dates:
        log.info("%s: no dated rows", ticker)
        return
    log.info("Last %d rows for %s:", len(dates), ticker)
    log.info("  %-12s %10s %10s %10s %10s", "date", "o", "h", "l", "c")
    for d in dates:
        r = node[d]
        def _n(v): return f"{v:10.4f}" if isinstance(v, (int, float)) else f"{'-':>10}"
        log.info("  %-12s %s %s %s %s", d, _n(r.get("o")), _n(r.get("h")),
                 _n(r.get("l")), _n(r.get("c")))


def _write_action(root, ticker: str, action: dict) -> dict[str, dict]:
    """
    Build the RTDB patch batch for a single action. per_field_fix rewrites the
    whole row (so a field going from wrong to right doesn't leave the row half-
    corrected); clamp only rewrites l and h. Returns the partial batch dict.
    """
    batch: dict[str, dict] = {}
    date = action["date"]
    if action["action"] == "per_field_fix":
        # Rewrite each corrected field at its own leaf, preserving anything
        # else the row carries (pc, ch, pch, volume, etc.). Do NOT rewrite the
        # whole row object — that would drop derived fields.
        for f in action["fields"]:
            batch[f"prices/{ticker}/{date}/{f}"] = action["after"][f]
    elif action["action"] == "clamp":
        for f in action["fields"]:
            batch[f"prices/{ticker}/{date}/{f}"] = action["after"][f]
    # report: no batch entries — logged only
    return batch


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", action="append",
                    help="Restrict to specific tickers (repeatable). Default: all.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually write to RTDB. Default is dry-run.")
    ap.add_argument("--backup", default="rtdb_ohlc_backup.json",
                    help="Where to save the original rows before writing.")
    ap.add_argument("--restore", help="Replay a backup file to undo an earlier run.")
    ap.add_argument("--dump", action="store_true",
                    help="Print the last 10 rows for each --ticker and exit. "
                         "Diagnostic only, no scan or write.")
    args = ap.parse_args()

    from pipeline.scripts.firebase_client import get_rtdb
    root = get_rtdb()

    if args.restore:
        data = json.loads(Path(args.restore).read_text())
        for r in data["rows"]:
            root.update({f"prices/{r['ticker']}/{r['date']}": r["before"]})
        print(f"Restored {len(data['rows'])} rows from {args.restore}")
        return

    if args.dump:
        if not args.ticker:
            log.error("--dump requires at least one --ticker")
            sys.exit(2)
        for t in args.ticker:
            node = root.child(f"prices/{t}").get()
            dump(t, node or {})
        return

    db = root.child("prices").get() or {}
    found = scan(db, args.ticker)

    by_action: dict[str, list[tuple[str, dict]]] = {"per_field_fix": [], "clamp": [], "report": []}
    for t, rows in found.items():
        for r in rows:
            by_action[r["action"]].append((t, r))

    n_fix    = len(by_action["per_field_fix"])
    n_clamp  = len(by_action["clamp"])
    n_report = len(by_action["report"])
    print(f"\nActions: {n_fix} per-field-fix, {n_clamp} clamp, {n_report} report-only "
          f"across {len(found)} tickers\n")

    if n_fix:
        print("─── per-field power-of-ten fixes ───")
        print(f"  {'tkr':<7}{'date':<12}{'reason'}")
        for t, r in sorted(by_action["per_field_fix"], key=lambda x: x[1]["date"], reverse=True)[:60]:
            print(f"  {t:<7}{r['date']:<12}{r['reason']}")
        print()

    if n_clamp:
        print("─── OHLC clamp (Open/Close as evidence) ───")
        print(f"  {'tkr':<7}{'date':<12}{'reason'}")
        for t, r in sorted(by_action["clamp"], key=lambda x: x[1]["date"], reverse=True)[:60]:
            print(f"  {t:<7}{r['date']:<12}{r['reason']}")
        print()

    if n_report:
        print("─── report only (no write) ───")
        print(f"  {'tkr':<7}{'date':<12}{'reason'}")
        for t, r in sorted(by_action["report"], key=lambda x: x[1]["date"], reverse=True)[:60]:
            print(f"  {t:<7}{r['date']:<12}{r['reason']}")
        print()

    if not args.apply:
        print("DRY RUN — nothing written. Pass --apply to write.")
        return

    writable = by_action["per_field_fix"] + by_action["clamp"]
    if not writable:
        print("No actionable fixes — nothing to write.")
        return

    backup = {"rows": [{"ticker": t, "date": r["date"], "before": r["before"]}
                       for t, r in writable]}
    Path(args.backup).write_text(json.dumps(backup, indent=1))
    log.info("Backup of %d rows written to %s", len(writable), args.backup)

    batch: dict = {}
    for t, r in writable:
        batch.update(_write_action(root, t, r))
        if len(batch) >= 500:
            root.update(batch); batch = {}
    if batch:
        root.update(batch)
    print(f"\nWrote {len(writable)} corrections. Undo with --restore {args.backup}")


if __name__ == "__main__":
    main()
