"""
validate_price_physics.py

Proves that decimal-shift corruption is PRESENT, using only the exchange's own
rules and the data's internal redundancy. It does not, and cannot, say which
value is the wrong one. Read-only, and it proposes no corrections at all.

THE LIMIT THIS MODULE HAS TO RESPECT
------------------------------------
An extreme percentage move proves an error exists in a PAIR of values. It does
not identify which half is wrong. An earlier version of this file assumed the
current close was the culprit and would have destroyed correct data:

    SMER 2025-11-03   c=15.00   pc=15.00   pch=0
    SMER 2025-11-04   c=15.00   pc=15.00   pch=-99      <- pc field is fine
    SMER 2025-11-05   c=15.00   pc= 0.15   pch=+9900    <- pc is the corrupt one
    SMER 2025-11-06   c=15.00   pc=15.00   pch=0

On 2025-11-05 the close of 15.00 is CORRECT and the prev-close field of 0.15 is
corrupt. Reading +9900% as "today is 100x too high" would have rewritten a good
15.00 down to 0.15. Deciding which side is wrong needs evidence this check does
not have — the surrounding run, or a verified anchor. That is what
detect_price_anomalies.py plus price_anchors.json are for.

So: this module flags pairs. Something else decides the direction.

WHY IT IS STILL WORTH HAVING
----------------------------
It is fully independent of price_anchors.json, whose bands were read off chart
axes by eye. Where the two agree on a date, the finding rests on two unrelated
lines of evidence rather than on anyone's reading of a chart.

1. THE NSE DAILY PRICE BAND
   The NSE applies a +/-10% daily limit to equity price movement. Measured over
   232,859 rows carrying a recorded pch, the distribution has a clean tail:

       |pch|     rows    reading
       10-15%    3,162   plausible - ex-dividend drops are band-exempt
       15-25%    2,277   unusual but possible on thin stocks
       25-50%    1,319   very unlikely in one session
       50-80%      552   not a real single-session move
       80-95%      187   ~ a x10 shift  (a x10 error reads as -90%)
       >95%        400   ~ a x100 shift (a x100 error reads as -99%)

   A move of -90% is not a market event on a band-limited exchange; it is a
   lost decimal place somewhere in that pair. The magnitude gives the size of
   the discrepancy — never which of the two values carries it.

2. PREV-CLOSE REDUNDANCY
   Each node carries pc alongside c. pc[T] tracks c[T-1] on 235,849 of 235,882
   rows, so the 33 that disagree are informative rather than noise. They caught
   CIC 2026-08-07 (c[T-1]=4.69 but pc=469.0, a x100 error) and EQTY 2007-10-04
   (c[T-1]=11.7 but pc=117.0) with no external input at all.

   Note ch is NOT usable this way: c - pc == ch on 100.0% of rows, meaning ch
   is derived rather than independently recorded, so it can never contradict c.

WHAT THIS DELIBERATELY DOES NOT DO
   Anything in the 25-80% zone is reported, never auto-corrected. Ex-dividend
   drops live near the bottom of that range - ABSA breaches the band on 2 May
   in 2019, 2023 and 2024, which is a dividend date, not corruption.

   AAPL is skipped: it is not NSE-listed, so the band does not apply to it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# The NSE daily band is 10%. Ex-dividend drops and band exemptions push
# legitimate moves a little past it, so certainty only begins much higher.
BAND_PCT = 10.0

# |pch| at or above this is treated as a decimal shift rather than a move.
# Chosen from the measured distribution: the 50-80% bucket holds 552 rows of
# implausible-but-ambiguous moves, while >=80% is where x10 (-90%) lands.
CERTAIN_PCT = 80.0

# Between the band and CERTAIN_PCT: reported, never corrected.
REVIEW_PCT = 25.0

NON_NSE = {"AAPL"}


def magnitude_from_pch(pch: float) -> int | None:
    """
    The order of magnitude implied by a move, e.g. -99% or +9900% -> 100.

    This says HOW BIG the discrepancy is. It deliberately does NOT say which
    side is wrong, and no caller may infer a correction from it. See the
    module docstring for why that distinction is load-bearing.
    """
    ratio = 1.0 + pch / 100.0
    if ratio <= 0:
        return None
    for f in (10, 100, 1000):
        if abs(ratio - 1.0 / f) <= 0.4 / f or abs(ratio - f) <= 0.4 * f:
            return f
    return None


def validate(db: dict) -> dict[str, list[dict]]:
    findings: dict[str, list[dict]] = defaultdict(list)

    for ticker in sorted(db):
        node = db[ticker]
        if not isinstance(node, dict) or ticker in NON_NSE:
            continue
        rows = sorted((d, v) for d, v in node.items() if isinstance(v, dict))
        prev_close = None

        for date, v in rows:
            c, pc, pch = v.get("c"), v.get("pc"), v.get("pch")

            # -- Check 1: implausible session move -------------------------
            if isinstance(pch, (int, float)) and abs(pch) > BAND_PCT:
                mag = abs(pch)
                if mag >= CERTAIN_PCT:
                    f = magnitude_from_pch(pch)
                    if f:
                        findings[ticker].append({
                            "date": date, "check": "band_breach",
                            "verdict": "suspect_pair", "close": c,
                            "pch": pch, "magnitude": f,
                            "why": (f"{pch:+.1f}% against a +/-{BAND_PCT:.0f}% band "
                                    f"proves a factor-of-{f} error involving this "
                                    f"row and the previous close — which of the two "
                                    f"is wrong is NOT determined by this check"),
                        })
                elif mag >= REVIEW_PCT:
                    findings[ticker].append({
                        "date": date, "check": "band_breach", "verdict": "review",
                        "close": c, "pch": pch,
                        "why": f"{pch:+.1f}% exceeds the band but is below the "
                               f"{CERTAIN_PCT:.0f}% certainty threshold",
                    })

            # -- Check 2: prev-close contradicts yesterday's close ----------
            if (prev_close and isinstance(pc, (int, float)) and pc > 0
                    and abs(pc - prev_close) > max(0.005, prev_close * 0.005)):
                ratio = pc / prev_close
                f = next((x for x in (10, 100, 1000)
                          if abs(ratio - x) < 0.4 * x or abs(ratio - 1 / x) < 0.4 / x),
                         None)
                findings[ticker].append({
                    "date": date, "check": "prev_close_mismatch",
                    "verdict": "suspect_pair" if f else "review",
                    "close": c, "pc": pc, "prev_close": prev_close,
                    "why": (f"pc={pc} contradicts yesterday's close {prev_close}"
                            + (f" by a factor of {f}" if f else "")),
                })

            if isinstance(c, (int, float)) and c > 0:
                prev_close = c

    return findings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file")
    ap.add_argument("--json")
    args = ap.parse_args()

    if args.from_file:
        db = json.load(open(args.from_file))
    else:
        from pipeline.scripts.firebase_client import get_rtdb
        db = get_rtdb().child("prices").get()

    findings = validate(db)
    certain = [(t, f) for t, fs in findings.items() for f in fs
               if f["verdict"] == "suspect_pair"]
    review = [(t, f) for t, fs in findings.items() for f in fs
              if f["verdict"] == "review"]

    print(f"\nSUSPECT PAIRS — a decimal error is proven present, but this check "
          f"does NOT identify which side is wrong ({len(certain)} rows)")
    print(f"  {'tkr':<7}{'date':<12}{'close':>10}{'pch':>12}  magnitude")
    for t, f in sorted(certain, key=lambda x: -abs(x[1].get("pch") or 0))[:15]:
        pch = f.get("pch")
        pchs = f"{pch:+.1f}%" if isinstance(pch, (int, float)) else "-"
        print(f"  {t:<7}{f['date']:<12}{f.get('close', 0):>10}{pchs:>12}"
              f"  factor {f.get('magnitude', '?')}")

    print(f"\nAMBIGUOUS — reported, never corrected ({len(review)} rows)")
    for t, f in sorted(review, key=lambda x: -abs(x[1].get("pch") or 0))[:8]:
        print(f"  {t:<7}{f['date']:<12}  {f['why']}")

    if args.json:
        json.dump(findings, open(args.json, "w"), indent=1)
        print(f"\nFull findings written to {args.json}")

    print("\nRead-only — nothing was modified.")


if __name__ == "__main__":
    main()
