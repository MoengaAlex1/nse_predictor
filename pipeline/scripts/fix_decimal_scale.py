"""
fix_decimal_scale.py

Repairs prices whose whole row was written at the wrong decimal scale, and
provides the guard that stops it happening again.

THE RULE
--------
NSE equities move within a +/-10% daily band. Prices therefore change
gradually — 8, 9, 10, 13, 15, 16, 19, 23, 22 — and no listing doubles in a
session, let alone moves by a factor of ten. So a close that is ~10x, ~100x or
~1000x the prevailing price is not a price move; it is a lost or gained decimal
point. 80 -> 8.0, 8.0 -> 80 and 422.3 -> 42.23 are all the same defect.

Whether the decimal was lost or gained is decided by looking at what the stock
was actually trading at over the four months either side of the suspect day. A
missing decimal reads as a tenth of that level; an added one reads as ten times
it.

WHY THE PREVIOUS CLOSE ALONE IS NOT ENOUGH
------------------------------------------
Comparing each row only against the row before it flags two days for every
fault: the corrupted day, and the day after, which merely looks wrong because
its predecessor is. Measured on live data, that naive comparison flags 154 rows
where only about half are actually wrong.

    2025-11-10  15.00   correct
    2025-11-11   0.15   CORRUPT      (0.01x the previous close)
    2025-11-12   0.15   CORRUPT
    2025-11-13   0.15   CORRUPT
    2025-11-14  15.00   correct, but reads as 100x its predecessor

The four-month median is unmoved by those three bad days, so 11-11 to 11-13 are
judged against 15.00 and corrected, while 11-14 matches the level and is left
alone. It also removes the failure mode where a series beginning part-way
through a corrupted run would invert the judgement entirely.

WHICH FIELDS MOVE
-----------------
The traded prices — c, o, h, l — scale together when the decimal point is
misread, so the factor applies to all of them.

pc does NOT. It is yesterday's close, and a scrape that gets today wrong often
still carries a correct pc: SMER 2025-11-11 arrived as c=0.15 with pc=15.00.
Scaling pc alongside c turned that correct 15.00 into 1500.00. pc, ch and pch
are instead rebuilt from the corrected series, which also repairs the day AFTER
a correction, whose pc would otherwise still point at the old wrong close.

Read-only unless --apply is passed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

log = logging.getLogger(__name__)

FACTORS = (10, 100, 1000)

# How close to an exact power of ten the ratio must sit. Generous enough to
# absorb a real day's movement on top of the scaling error, tight enough that
# an ordinary move can never reach it — the nearest real move to 10x is a
# doubling, which no NSE session produces.
TOLERANCE = 0.15

# Fields that scale together when the decimal point is misread.
#
# pc is deliberately NOT here. It is yesterday's close, and a scrape that
# mis-reads today's decimal point often still carries a correct pc — SMER
# 2025-11-11 arrived as c=0.15 with pc=15.00, where only the close was wrong.
# Scaling pc alongside c turned a correct 15.00 into 1500.00. pc is instead
# rebuilt from the preceding corrected close by rebuild_prev_close().
SCALED_FIELDS = ("c", "o", "h", "l")

# Half-width of the window used to establish what a stock was actually trading
# at. Four months either side is long enough that mis-scaled days are always
# outnumbered, and short enough that a genuine trend does not distort the level.
WINDOW_DAYS = 122

# Below this many surrounding rows there is not enough context to judge, so the
# row is left alone rather than guessed at.
MIN_WINDOW_ROWS = 5

# Share of the window that must sit at one order of magnitude before a
# correction is trusted. Where corruption alternates, the window is split and
# the median is no longer evidence of the true level, so the row is declined.
WINDOW_MAJORITY = 0.70


def scale_error(close: float, anchor: float) -> int | None:
    """
    Return the factor by which `close` is mis-scaled against `anchor`, or None.

    Positive means the value is too large and must be divided; negative means
    it is too small and must be multiplied.
    """
    if not close or not anchor or close <= 0 or anchor <= 0:
        return None
    ratio = close / anchor
    for f in FACTORS:
        if abs(ratio - f) <= f * TOLERANCE:
            return f
        if abs(ratio - 1.0 / f) <= (1.0 / f) * TOLERANCE:
            return -f
    return None


def correct_row(row: dict, factor: int) -> dict:
    """
    Apply the inverse of `factor` to the traded prices.

    pc, ch and pch are left for rebuild_prev_close, which derives them from the
    corrected series. Scaling pc here would corrupt the rows where the scrape
    got yesterday's close right and only today's wrong.
    """
    out = dict(row)
    for key in SCALED_FIELDS:
        v = out.get(key)
        if isinstance(v, (int, float)) and v:
            out[key] = round(v / factor if factor > 0 else v * -factor, 4)
    return out


def rebuild_prev_close(node: dict, corrections: dict[str, dict]) -> dict[str, dict]:
    """
    Rebuild pc, ch and pch across a ticker from the corrected closes.

    Two things go stale once a close changes, and neither is fixed by scaling
    the row in isolation:

      * a corrected row may carry a pc that was always right, so it must not be
        scaled — only re-derived;
      * the row AFTER a correction still points at the old, wrong close, which
        is why recovery days were left reading pch = 9900%.

    Returns {date: row} for every row that needs writing, corrections included.
    """
    merged = {d: dict(v) for d, v in node.items()
              if isinstance(v, dict) and isinstance(v.get("c"), (int, float))}
    for d, row in corrections.items():
        merged[d] = dict(row)

    out: dict[str, dict] = {}
    prev_close: float | None = None
    for date in sorted(merged):
        row = merged[date]
        close = row.get("c")
        if not isinstance(close, (int, float)) or close <= 0:
            continue
        if prev_close is not None:
            new_pc = round(prev_close, 4)
            new_ch = round(close - new_pc, 4)
            new_pch = round((close - new_pc) / new_pc * 100, 4) if new_pc else 0.0
            original = node.get(date, {})
            if (date in corrections
                    or original.get("pc") != new_pc
                    or original.get("ch") != new_ch):
                row = {**row, "pc": new_pc, "ch": new_ch, "pch": new_pch}
                out[date] = row
        elif date in corrections:
            out[date] = row
        prev_close = close
    return out


def local_level(rows: list[tuple[str, dict]], index: int) -> float | None:
    """
    The prevailing price around `index`, taken as the median close over a
    +/-WINDOW_DAYS window with the row itself excluded.

    A median is used rather than the neighbouring close because corruption
    arrives in runs, so an adjacent value is often wrong too. Over four months
    of trading the mis-scaled days are always a minority, which is exactly the
    condition a median needs to land on the true level. That is what makes the
    direction of the error decidable: compare the suspect close against the
    level the stock was actually trading at, and a missing decimal reads as
    1/10th of it while an added one reads as 10x.
    """
    date = datetime.date.fromisoformat(rows[index][0])
    lo = (date - datetime.timedelta(days=WINDOW_DAYS)).isoformat()
    hi = (date + datetime.timedelta(days=WINDOW_DAYS)).isoformat()

    window = [r["c"] for i, (d, r) in enumerate(rows)
              if i != index and lo <= d <= hi]
    if len(window) < MIN_WINDOW_ROWS:
        return None
    window.sort()
    return window[len(window) // 2]


def load_floors(path: str | None = None) -> dict:
    """
    Per-company plausible price ranges (pipeline/config/price_floors.json).

    A close outside a company's verified range is corrupt by definition. That
    is independent evidence, so it settles rows the surrounding window cannot —
    see the note in that file on SMER's alternating 2019-2021 history.
    """
    p = Path(path) if path else Path(__file__).parent.parent / "config" / "price_floors.json"
    if not p.exists():
        return {}
    return {k: v for k, v in json.loads(p.read_text()).items() if not k.startswith("_")}


def violates_floor(close: float, floor: dict | None) -> bool:
    """True when the close falls outside the company's verified range."""
    if not floor:
        return False
    lo, hi = floor.get("min"), floor.get("max")
    if lo is not None and close < lo:
        return True
    if hi is not None and close > hi:
        return True
    return False


def factor_towards(close: float, level: float, floor: dict | None) -> int | None:
    """
    Choose the power of ten that moves `close` closest to `level`.

    Used when a floor has already established the row is corrupt. The floor
    alone cannot pick the factor — 0.15 satisfies a 1.00 floor at both x10 and
    x100 — so the prevailing price decides between 1.50 and 15.00.
    """
    best, best_gap = None, None
    for f in FACTORS:
        for cand, signed in ((close * f, -f), (close / f, f)):
            if floor and violates_floor(cand, floor):
                continue
            gap = abs(cand - level) / level if level else abs(cand - close)
            if best_gap is None or gap < best_gap:
                best, best_gap = signed, gap
    return best


def find_bad_rows(node: dict, floor: dict | None = None) -> list[dict]:
    """
    Judge every row against the prevailing price around it.

    Comparing against the previous close alone is not enough: it flags the
    recovery day as well as the corrupt one, and it inverts entirely if a
    series happens to begin part-way through a corrupted run. A +/-4 month
    median has neither problem, because it is unmoved by a handful of bad days
    wherever they sit.
    """
    rows = [(d, v) for d, v in sorted(node.items())
            if isinstance(v, dict) and isinstance(v.get("c"), (int, float)) and v["c"] > 0]
    if len(rows) < MIN_WINDOW_ROWS:
        return []

    out: list[dict] = []
    for i, (date, row) in enumerate(rows):
        close = row["c"]
        level = local_level(rows, i)
        if level is None:
            continue                    # too little surrounding history to judge

        # A verified floor is independent evidence that the row is wrong, so it
        # settles cases the window cannot. The window still picks the factor.
        if violates_floor(close, floor):
            factor = factor_towards(close, level, floor)
            if factor is None:
                continue
            out.append({"date": date, "before": row, "after": correct_row(row, factor),
                        "factor": factor, "anchor": level, "reason": "outside verified range"})
            continue

        factor = scale_error(close, level)
        if factor is None:
            continue
        if not _window_is_decisive(rows, i, level):
            continue                    # ambiguous — see _window_is_decisive
        out.append({"date": date, "before": row, "after": correct_row(row, factor),
                    "factor": factor, "anchor": level, "reason": "power-of-ten vs window"})
    return out


def _window_is_decisive(rows: list[tuple[str, dict]], index: int, level: float) -> bool:
    """
    True when the surrounding window clearly sits at one order of magnitude.

    A median only identifies the true price level while the mis-scaled days are
    a MINORITY. Where corruption alternates that stops holding, and the median
    can land on the wrong level — which would invert the correction and damage
    a good row.

    SMER during 2019-2021 is the real case: it spends 355 days at ~3.00 and 200
    days at ~0.30, so some four-month windows are majority-corrupt. Judged by
    median alone, the sound close of 3.37 on 2021-07-12 gets "corrected" to
    0.337 against an anchor of 0.375 that is itself corrupt.

    Requiring a clear majority at one magnitude makes the fixer decline those
    rows instead of guessing. They are reported for review, not silently
    altered.
    """
    date = datetime.date.fromisoformat(rows[index][0])
    lo = (date - datetime.timedelta(days=WINDOW_DAYS)).isoformat()
    hi = (date + datetime.timedelta(days=WINDOW_DAYS)).isoformat()

    window = [r["c"] for i, (d, r) in enumerate(rows) if i != index and lo <= d <= hi]
    if not window:
        return False

    # Share of the window within half a decade of the level either way, i.e.
    # genuinely at the same order of magnitude.
    agreeing = sum(1 for c in window if level / 3.2 <= c <= level * 3.2)
    return agreeing / len(window) >= WINDOW_MAJORITY


def scan(db: dict, tickers: list[str] | None = None,
         floors: dict | None = None) -> dict[str, list[dict]]:
    floors = load_floors() if floors is None else floors
    found = {}
    for ticker in sorted(db):
        if tickers and ticker not in tickers:
            continue
        node = db[ticker]
        if not isinstance(node, dict):
            continue
        bad = find_bad_rows(node, floors.get(ticker))
        if bad:
            # Rebuild pc/ch/pch across the ticker so corrected rows and the
            # recovery days after them stay consistent with the new closes.
            rebuilt = rebuild_prev_close(node, {b["date"]: b["after"] for b in bad})
            by_date = {b["date"]: b for b in bad}
            merged = []
            for date in sorted(rebuilt):
                b = by_date.get(date)
                merged.append({
                    "date": date,
                    "before": node.get(date, {}),
                    "after": rebuilt[date],
                    "factor": b["factor"] if b else None,
                    "anchor": b["anchor"] if b else None,
                    "reason": b["reason"] if b else "prev-close rebuilt after correction",
                })
            found[ticker] = merged
    return found


def is_safe_to_write(close: float, previous_close: float | None) -> bool:
    """
    Guard for the ingest path. False means the row is mis-scaled and must not
    be written. Use before persisting any scraped row.
    """
    if previous_close is None:
        return True                    # nothing to compare against yet
    return scale_error(close, previous_close) is None


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", action="append")
    ap.add_argument("--from-file")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", default="decimal_scale_backup.json")
    ap.add_argument("--restore")
    ap.add_argument("--remove-nontrading", action="store_true",
                    help="Delete rows dated on days the NSE was closed. The "
                         "exchange does not trade at weekends or on Kenyan "
                         "public holidays, so such a row cannot be a session.")
    ap.add_argument("--rebuild-derived", action="store_true",
                    help="Only rebuild pc/ch/pch from the existing closes. Use "
                         "after a correction run, or to repair rows whose "
                         "prev-close no longer matches the day before.")
    args = ap.parse_args()

    if args.restore:
        from pipeline.scripts.firebase_client import get_rtdb
        data = json.loads(Path(args.restore).read_text())
        root = get_rtdb()
        for r in data["rows"]:
            root.update({f"prices/{r['ticker']}/{r['date']}": r["before"]})
        print(f"Restored {len(data['rows'])} rows")
        return

    if args.from_file:
        db = json.load(open(args.from_file))
    else:
        from pipeline.scripts.firebase_client import get_rtdb
        db = get_rtdb().child("prices").get()

    if args.remove_nontrading:
        from pipeline.scripts.nse_calendar import is_trading_day
        from pipeline.scripts.firebase_client import get_rtdb
        doomed = []
        for ticker in sorted(db):
            if args.ticker and ticker not in args.ticker:
                continue
            node = db[ticker]
            if not isinstance(node, dict):
                continue
            for date, row in sorted(node.items()):
                if isinstance(row, dict) and not is_trading_day(date):
                    doomed.append((ticker, date, row))
        print(f"\nRows dated on days the NSE was closed: {len(doomed)}")
        for t, d, r in doomed[:15]:
            import datetime as _dt
            print(f"  {t:<7}{d}  {_dt.date.fromisoformat(d).strftime('%a')}  c={r.get('c')}")
        if not args.apply:
            print("\nDRY RUN — nothing removed. Pass --apply to delete.")
            return
        Path(args.backup).write_text(json.dumps(
            {"rows": [{"ticker": t, "date": d, "before": r} for t, d, r in doomed]}, indent=1))
        log.info("Backup of %d rows written to %s", len(doomed), args.backup)
        root = get_rtdb()
        batch = {}
        for t, d, _ in doomed:
            batch[f"prices/{t}/{d}"] = None
            if len(batch) >= 500:
                root.update(batch); batch = {}
        if batch:
            root.update(batch)
        print(f"\nRemoved {len(doomed)} non-trading rows. Undo with --restore {args.backup}")
        return

    if args.rebuild_derived:
        found = {}
        for ticker in sorted(db):
            if args.ticker and ticker not in args.ticker:
                continue
            node = db[ticker]
            if not isinstance(node, dict):
                continue
            rebuilt = rebuild_prev_close(node, {})
            if rebuilt:
                found[ticker] = [{"date": d, "before": node.get(d, {}),
                                  "after": rebuilt[d], "factor": None,
                                  "anchor": node.get(d, {}).get("c"),
                                  "reason": "prev-close rebuilt"}
                                 for d in sorted(rebuilt)]
    else:
        found = scan(db, args.ticker)
    total = sum(len(v) for v in found.values())

    label = "Rows with stale prev-close" if args.rebuild_derived else "Mis-scaled rows"
    print(f"\n{label}: {total} across {len(found)} tickers\n")
    print(f"  {'tkr':<7}{'date':<12}{'anchor':>11}{'wrong':>12}{'corrected':>12}")
    flat = []
    for t, rows in found.items():
        for r in rows:
            flat.append((t, r))
    for t, r in sorted(flat, key=lambda x: x[1]["date"], reverse=True)[:30]:
        # anchor and the original close are absent on rebuild-only rows, where
        # nothing about the price changed and only pc/ch/pch were re-derived.
        def _num(v):
            return f"{v:>11.4f}" if isinstance(v, (int, float)) else f"{'-':>11}"
        print(f"  {t:<7}{r['date']:<12}{_num(r.get('anchor'))}"
              f"{_num(r.get('before', {}).get('c'))}{_num(r.get('after', {}).get('c'))}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Pass --apply to write.")
        return

    from pipeline.scripts.firebase_client import get_rtdb
    backup = {"rows": [{"ticker": t, "date": r["date"], "before": r["before"]}
                       for t, r in flat]}
    Path(args.backup).write_text(json.dumps(backup, indent=1))
    log.info("Backup of %d rows written to %s", len(flat), args.backup)

    root = get_rtdb()
    batch = {}
    for t, r in flat:
        batch[f"prices/{t}/{r['date']}"] = r["after"]
        if len(batch) >= 500:
            root.update(batch); batch = {}
    if batch:
        root.update(batch)
    print(f"\nCorrected {len(flat)} rows. Undo with --restore {args.backup}")


if __name__ == "__main__":
    main()
