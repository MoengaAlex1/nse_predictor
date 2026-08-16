"""
clamp_rtdb_ohlc.py

Fixes per-field decimal-shift errors that fix_decimal_scale.py can't see. That
script judges rows by Close alone and scales all four OHLC fields together, so
rows where only Low or High got a wrong decimal (while Open and Close stayed
correct) slip through — the row-level median never fires and every downstream
detector that compares against the adjacent day gets confused.

The evidence used here is intrinsic to the row itself: on the NSE, every session
satisfies

    Low <= min(Open, Close) <= max(Open, Close) <= High

so a row where Low > min(Open, Close) or High < max(Open, Close) is broken by
definition. The correction is derived from the row's own Open and Close:

    correct_low  = min(Open, Close)
    correct_high = max(Open, Close)

No lookup table, no ticker-specific values, no adjacent-day comparison. This is
the same algorithm nse_price_cleaner.py:clamp_ohlc() already applies to the
cleaned CSVs — this script applies it to RTDB, which is what actually feeds the
dashboard for the current week (the CSVs lag by a few days).

SAFETY GUARDS
-------------
1. If Open and Close disagree by more than SAFETY_SPREAD_PCT of Close, the row
   is skipped. That spread means Open or Close is itself an OCR error, and the
   min/max-of-(O,C) rule would land on the wrong anchor.
2. Only Low and High are ever modified. Open and Close are the evidence used to
   pick the correction, so mutating them here would be circular.
3. Every write is preceded by a backup of the original row to a JSON file, so
   the run can be reversed.

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

log = logging.getLogger(__name__)

# If Open and Close differ by more than this share of Close, one of them is
# almost certainly wrong and the min/max-of-(O,C) anchor cannot be trusted.
# Matches the guard in nse_price_cleaner.py:clamp_ohlc().
SAFETY_SPREAD_PCT = 0.40

PRICE_FIELDS = ("o", "h", "l", "c")


def find_violations(node: dict) -> list[dict]:
    """
    Return the list of rows in this ticker's node whose OHLC fields are
    self-inconsistent. Each element carries the original row plus the proposed
    corrected Low and High derived from the row's own Open and Close.
    """
    out: list[dict] = []
    for date in sorted(node):
        row = node[date]
        if not isinstance(row, dict):
            continue
        vals = {f: row.get(f) for f in PRICE_FIELDS}
        if any(not isinstance(v, (int, float)) or v <= 0 for v in vals.values()):
            continue

        o, h, l, c = vals["o"], vals["h"], vals["l"], vals["c"]

        # Guard against Open or Close being the field that's actually wrong.
        # When that spread is large, min/max of (O, C) does not describe the
        # real intraday range.
        if abs(o - c) > SAFETY_SPREAD_PCT * c:
            continue

        correct_low = min(o, c)
        correct_high = max(o, c)

        low_wrong  = l > correct_low
        high_wrong = h < correct_high
        crossed    = l > h                         # Low > High is impossible

        if not (low_wrong or high_wrong or crossed):
            continue

        new_l = correct_low if low_wrong or crossed else l
        new_h = correct_high if high_wrong or crossed else h

        # After clamping, Low must still be <= High. If clamping only one of
        # them would leave the row crossed, clamp both to their derived values.
        if new_l > new_h:
            new_l, new_h = correct_low, correct_high

        # Nothing to do if the "fix" would just restate the current values.
        if new_l == l and new_h == h:
            continue

        reasons = []
        if crossed:      reasons.append(f"L({l})>H({h})")
        if low_wrong:    reasons.append(f"L({l})>min(O,C)={correct_low}")
        if high_wrong:   reasons.append(f"H({h})<max(O,C)={correct_high}")

        out.append({
            "date":   date,
            "before": dict(row),
            "after":  {**row, "l": round(new_l, 4), "h": round(new_h, 4)},
            "reason": "; ".join(reasons),
            "l_before": l, "l_after": round(new_l, 4),
            "h_before": h, "h_after": round(new_h, 4),
        })
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

    total = sum(len(v) for v in found.values())
    print(f"\nOHLC-inconsistent rows: {total} across {len(found)} tickers\n")
    print(f"  {'tkr':<7}{'date':<12}{'reason':<45}"
          f"{'l':>10}{'l→':>10}{'h':>10}{'h→':>10}")

    flat: list[tuple[str, dict]] = []
    for t, rows in found.items():
        for r in rows:
            flat.append((t, r))

    for t, r in sorted(flat, key=lambda x: x[1]["date"], reverse=True)[:60]:
        print(f"  {t:<7}{r['date']:<12}{r['reason']:<45}"
              f"{r['l_before']:>10.4f}{r['l_after']:>10.4f}"
              f"{r['h_before']:>10.4f}{r['h_after']:>10.4f}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Pass --apply to write.")
        return

    backup = {"rows": [{"ticker": t, "date": r["date"], "before": r["before"]}
                       for t, r in flat]}
    Path(args.backup).write_text(json.dumps(backup, indent=1))
    log.info("Backup of %d rows written to %s", len(flat), args.backup)

    batch: dict[str, dict] = {}
    for t, r in flat:
        # Update only l and h — Open and Close were the evidence, mutating them
        # here would be circular.
        batch[f"prices/{t}/{r['date']}/l"] = r["l_after"]
        batch[f"prices/{t}/{r['date']}/h"] = r["h_after"]
        if len(batch) >= 500:
            root.update(batch); batch = {}
    if batch:
        root.update(batch)
    print(f"\nClamped {len(flat)} rows. Undo with --restore {args.backup}")


if __name__ == "__main__":
    main()
