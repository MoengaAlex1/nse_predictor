"""
detect_price_anomalies.py

Finds decimal-shift corruption in the RTDB price history and proposes
corrections. Read-only by default — writes nothing unless --apply is passed.

WHY THIS EXISTS
---------------
fix_all_decimals.py only detects an *isolated single-day* spike: it requires a
>=10x ratio against both the previous and the next value. When the corruption
spans several consecutive days, every day in the run fails that test, because
each bad day's neighbour is also bad:

    2025-11-10  15.00
    2025-11-11   0.15   prev 100x OK, next 1x FAIL  -> missed
    2025-11-12   0.15   prev   1x FAIL              -> missed
    2025-11-13   0.15   prev   1x FAIL, next 100x   -> missed
    2025-11-14  15.00

This module works on *runs* rather than single days.

THE SAFETY PROBLEM
------------------
Several NSE companies genuinely trade at very low prices. Measured from live
data: UCHM has traded as low as 0.16, HAFR 0.27, EVRD 0.61, KQ 0.86. Nine
tickers have a median price under 5 KES.

So a rule like "below 1.00 KES must be a decimal error" would multiply
legitimate prices tenfold and corrupt exactly the companies it claims to fix.

Every check below is therefore RELATIVE to the ticker's own local price level.
There is deliberately no absolute price threshold anywhere in this file. A
correction is proposed only when all four conditions hold:

  1. The run is bounded — price returns to the prior level afterwards. A
     permanent move is a real market event, not corruption. This is what
     protects UCHM's genuine multi-year decline from 20.00 to 0.20.
  2. The flanks agree with each other. If the price before differs materially
     from the price after, the series is unstable for other reasons and we
     cannot attribute the gap to a decimal shift. This is what rejects TOTL,
     whose flanks read 16.98 before and 31.25 after.
  3. Multiplying the run by exactly 10, 100 or 1000 restores continuity with
     the flanks to within RESTORE_TOL.
  4. No other power of ten also fits, so the correction is unambiguous.

Anything failing these is reported for human review, never auto-corrected.

USAGE
  python pipeline/scripts/detect_price_anomalies.py                # report all
  python pipeline/scripts/detect_price_anomalies.py --ticker SMER
  python pipeline/scripts/detect_price_anomalies.py --json out.json
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics as st
from dataclasses import dataclass, asdict, field

log = logging.getLogger(__name__)

# A run must sit at least this far below/above its flanks to be a candidate.
# Well under 10 so near-miss shifts are still surfaced for review.
CANDIDATE_RATIO = 4.0

# After applying the factor, the run median must land within this fraction of
# the flank median. Empirically SMER's true shifts land within 0.07.
RESTORE_TOL = 0.20

# The price before and after the run must agree within this fraction, else the
# series is unstable and the gap cannot be attributed to a decimal shift.
FLANK_AGREE_TOL = 0.35

# Trading days sampled either side of a run to establish the local level.
FLANK_DAYS = 6

# Values inside a run must be flat within this fraction to count as one run.
RUN_COHESION_TOL = 0.35

FACTORS = (10, 100, 1000)


@dataclass
class Anomaly:
    ticker: str
    start: str
    end: str
    days: int
    run_median: float
    flank_before: float
    flank_after: float
    verdict: str                     # "correctable" | "review"
    factor: int | None = None
    corrected_to: float | None = None
    reason: str = ""
    dates: list[str] = field(default_factory=list)


def _series(node: dict) -> list[tuple[str, float]]:
    """[(date, close)] sorted by date, skipping missing closes."""
    out = []
    for d, v in node.items():
        if isinstance(v, dict) and isinstance(v.get("c"), (int, float)) and v["c"] > 0:
            out.append((d, float(v["c"])))
    out.sort()
    return out


def _find_runs(series: list[tuple[str, float]]) -> list[tuple[int, int]]:
    """
    Index spans [i, j] where the price steps away from the preceding level by
    at least CANDIDATE_RATIO and stays cohesive. Direction-agnostic, so both
    dropped digits (too low) and added digits (too high) are found.
    """
    runs, n, k = [], len(series), 1
    while k < n:
        prev = series[k - 1][1]
        cur = series[k][1]
        ratio = prev / cur if cur < prev else cur / prev
        if ratio < CANDIDATE_RATIO:
            k += 1
            continue
        j = k
        while (j + 1 < n
               and abs(series[j + 1][1] - series[k][1]) / series[k][1] <= RUN_COHESION_TOL):
            j += 1
        runs.append((k, j))
        k = j + 1
    return runs


def _median_around(series, lo: int, hi: int) -> tuple[float | None, float | None]:
    before = [p for _, p in series[max(0, lo - FLANK_DAYS):lo]]
    after = [p for _, p in series[hi + 1:hi + 1 + FLANK_DAYS]]
    return (st.median(before) if before else None,
            st.median(after) if after else None)


def analyse_ticker(ticker: str, node: dict) -> list[Anomaly]:
    series = _series(node)
    if len(series) < FLANK_DAYS * 2:
        return []

    out: list[Anomaly] = []
    for lo, hi in _find_runs(series):
        run = [p for _, p in series[lo:hi + 1]]
        run_med = st.median(run)
        before, after = _median_around(series, lo, hi)
        a = Anomaly(
            ticker=ticker, start=series[lo][0], end=series[hi][0],
            days=hi - lo + 1, run_median=round(run_med, 4),
            flank_before=round(before, 4) if before else None,
            flank_after=round(after, 4) if after else None,
            verdict="review",
            dates=[d for d, _ in series[lo:hi + 1]],
        )

        # 1. Bounded? An unbounded move is a real regime change, not corruption.
        #    This is what keeps UCHM's genuine long decline untouched.
        if before is None or after is None:
            a.reason = "run touches the edge of the series; no flank to compare"
            out.append(a)
            continue

        # 2. Do the flanks agree with each other?
        if abs(before - after) / max(before, after) > FLANK_AGREE_TOL:
            a.reason = (f"flanks disagree ({before:.2f} vs {after:.2f}); series is "
                        f"unstable here, gap cannot be attributed to a decimal shift")
            out.append(a)
            continue

        flank_med = st.median([before, after])

        # 3/4. Exactly one power of ten must restore continuity.
        fits = []
        for f in FACTORS:
            for cand in (run_med * f, run_med / f):
                if abs(cand - flank_med) / flank_med <= RESTORE_TOL:
                    fits.append((f if cand > run_med else -f, cand))
        if not fits:
            a.reason = (f"no power of ten restores continuity "
                        f"(run {run_med:.2f} vs flanks {flank_med:.2f})")
        elif len(fits) > 1:
            a.reason = f"ambiguous: {len(fits)} factors fit equally well"
        else:
            factor, corrected = fits[0]
            a.verdict = "correctable"
            a.factor = factor
            a.corrected_to = round(corrected, 4)
            a.reason = (f"x{abs(factor)} restores continuity to within "
                        f"{abs(corrected - flank_med) / flank_med * 100:.1f}% of flanks")
        out.append(a)
    return out


def analyse_all(db: dict) -> list[Anomaly]:
    found = []
    for ticker in sorted(db):
        node = db[ticker]
        if isinstance(node, dict):
            found.extend(analyse_ticker(ticker, node))
    return found


def _load_db(path: str | None) -> dict:
    if path:
        with open(path) as fh:
            return json.load(fh)
    from pipeline.scripts.firebase_client import get_rtdb
    return get_rtdb().child("prices").get()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", help="Only analyse this ticker")
    ap.add_argument("--from-file", help="Read a prices JSON dump instead of RTDB")
    ap.add_argument("--json", help="Write full findings to this path")
    args = ap.parse_args()

    db = _load_db(args.from_file)
    if args.ticker:
        db = {args.ticker: db.get(args.ticker, {})}

    found = analyse_all(db)
    correctable = [a for a in found if a.verdict == "correctable"]
    review = [a for a in found if a.verdict == "review"]

    print(f"\nCORRECTABLE — one power of ten restores continuity ({len(correctable)} runs, "
          f"{sum(a.days for a in correctable)} days)")
    print(f"  {'tkr':<7}{'start':<12}{'end':<12}{'d':>4}{'run':>9}{'->':>4}{'fixed':>9}   flanks")
    for a in sorted(correctable, key=lambda x: -x.days)[:25]:
        op = "x" if a.factor > 0 else "/"
        print(f"  {a.ticker:<7}{a.start:<12}{a.end:<12}{a.days:>4}{a.run_median:>9.2f}"
              f"{op + str(abs(a.factor)):>5}{a.corrected_to:>9.2f}   "
              f"{a.flank_before:.2f}/{a.flank_after:.2f}")

    print(f"\nNEEDS REVIEW — not auto-correctable ({len(review)} runs, "
          f"{sum(a.days for a in review)} days)")
    for a in sorted(review, key=lambda x: -x.days)[:15]:
        print(f"  {a.ticker:<7}{a.start:<12}{a.end:<12}{a.days:>4}  {a.reason}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump([asdict(a) for a in found], fh, indent=1)
        print(f"\nFull findings written to {args.json}")

    print("\nNothing was modified — this tool is read-only.")


if __name__ == "__main__":
    main()
