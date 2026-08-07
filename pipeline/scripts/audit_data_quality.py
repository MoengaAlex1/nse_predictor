"""
audit_data_quality.py

Whole-dataset health report for the RTDB price history. Read-only.

Decimal-shift corruption (see detect_price_anomalies.py) is one problem among
several, and fixing it alone would leave the rest invisible. This enumerates
every class of defect so the actual scope is known before anything is changed.

Checks, and why each matters:

  decimal_shift      Order-of-magnitude corruption. Distorts charts and any
                     model trained on the series. Correctable only where an
                     external anchor exists.
  ohlc_invalid       high < low, or close outside [low, high]. A row that
                     cannot be a real trading day, so the parse is wrong.
  frozen_run         The identical close repeated for many sessions. Usually
                     forward-fill masquerading as real trading, which flattens
                     volatility and biases models toward "no movement".
  zero_volume_price  A price printed with no volume. Often a carried-forward
                     quote rather than an actual trade.
  session_gap        Missing trading sessions. Counted against the real NSE
                     calendar (Mon-Fri minus Kenyan public holidays), never
                     raw calendar days, which overstates gaps badly.
  future_date        Dates beyond today. Always a bug.
  weekend_row        Saturday/Sunday rows. The NSE does not trade then.
  holiday_row        Rows dated on a Kenyan public holiday - the exchange was
                     closed, so the row cannot be a real session.
  unknown_ticker     Present in RTDB but absent from companies.json, so nothing
                     in the app maps to it and it is silently dead weight.

Usage:
  python pipeline/scripts/audit_data_quality.py
  python pipeline/scripts/audit_data_quality.py --from-file dump.json
  python pipeline/scripts/audit_data_quality.py --json report.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Repo root on sys.path so `pipeline.*` imports work when run as a script.
_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# A close repeated at least this many sessions running is treated as frozen.
FROZEN_MIN = 15

# A gap of at least this many missed TRADING SESSIONS is reported.
# Sessions, never calendar days — the NSE trades Mon-Fri minus public holidays.
GAP_MIN_SESSIONS = 10


from pipeline.scripts.nse_calendar import is_trading_day as _is_trading_day


def _rows(node: dict) -> list[tuple[str, dict]]:
    return sorted((d, v) for d, v in node.items() if isinstance(v, dict))


def audit_ticker(ticker: str, node: dict, today: str) -> dict:
    rows = _rows(node)
    issues: dict[str, list] = defaultdict(list)
    if not rows:
        return issues

    closes = [(d, v["c"]) for d, v in rows
              if isinstance(v.get("c"), (int, float)) and v["c"] > 0]

    for d, v in rows:
        c, h, l = v.get("c"), v.get("h"), v.get("l")
        if all(isinstance(x, (int, float)) for x in (c, h, l)):
            if h < l or not (l <= c <= h):
                issues["ohlc_invalid"].append({"date": d, "o": v.get("o"),
                                               "h": h, "l": l, "c": c})
        if d > today:
            issues["future_date"].append({"date": d, "c": c})
        try:
            dt = datetime.date.fromisoformat(d)
            if dt.weekday() >= 5:
                issues["weekend_row"].append({"date": d, "c": c})
            elif not _is_trading_day(dt):
                issues["holiday_row"].append({"date": d, "c": c})
        except ValueError:
            issues["bad_date_format"].append({"date": d})

        if isinstance(c, (int, float)) and c > 0 and v.get("v") in (0, None):
            issues["zero_volume_price"].append({"date": d, "c": c})

    # Frozen runs: identical close repeated session after session.
    i = 0
    while i < len(closes):
        j = i
        while j + 1 < len(closes) and closes[j + 1][1] == closes[i][1]:
            j += 1
        if j - i + 1 >= FROZEN_MIN:
            issues["frozen_run"].append({
                "start": closes[i][0], "end": closes[j][0],
                "days": j - i + 1, "price": closes[i][1],
            })
        i = j + 1

    # Gaps, counted in TRADING SESSIONS. Counting calendar days overstates
    # badly: 24 Dec to 2 Jan is 9 calendar days but only 3 missed sessions once
    # weekends, Christmas, Boxing Day and New Year are removed.
    from pipeline.scripts.nse_calendar import sessions_missed
    for (d1, _), (d2, _) in zip(closes, closes[1:]):
        try:
            missed = sessions_missed(d1, d2)
        except ValueError:
            continue
        if missed >= GAP_MIN_SESSIONS:
            issues["session_gap"].append({"from": d1, "to": d2, "days": missed})

    return issues


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

    from pipeline.config import load_companies
    known = {c["short"].upper() for c in load_companies()}

    today = datetime.date.today().isoformat()
    report: dict[str, dict] = {}
    for t in sorted(db):
        if isinstance(db[t], dict):
            report[t] = audit_ticker(t, db[t], today)

    # Decimal shifts come from the dedicated detector so there is one source
    # of truth for that rule rather than a second, drifting copy.
    from pipeline.scripts.detect_price_anomalies import analyse_all
    for a in analyse_all(db):
        report.setdefault(a.ticker, defaultdict(list))
        key = "decimal_shift" if a.verdict == "correctable" else "needs_review"
        report[a.ticker][key].append({
            "start": a.start, "end": a.end, "days": a.days, "reason": a.reason,
        })

    unknown = sorted(set(report) - known)

    totals = Counter()
    for t, issues in report.items():
        for kind, items in issues.items():
            totals[kind] += sum(i.get("days", 1) for i in items)

    print(f"\n{'=' * 66}\nDATA QUALITY AUDIT — {len(report)} tickers\n{'=' * 66}")
    print(f"\n{'issue':<22}{'affected days':>15}{'tickers':>10}")
    for kind, n in totals.most_common():
        ntick = sum(1 for t in report if report[t].get(kind))
        print(f"{kind:<22}{n:>15,}{ntick:>10}")

    print(f"\n{'-' * 66}\nWORST AFFECTED TICKERS\n{'-' * 66}")
    per = {t: sum(sum(i.get("days", 1) for i in v) for v in iss.values())
           for t, iss in report.items()}
    for t, n in sorted(per.items(), key=lambda x: -x[1])[:12]:
        kinds = ", ".join(f"{k}:{len(v)}" for k, v in report[t].items() if v)
        print(f"  {t:<7}{n:>7,} days   {kinds}")

    if unknown:
        print(f"\n{'-' * 66}\nUNKNOWN TICKERS — in RTDB but not companies.json\n{'-' * 66}")
        print("  " + ", ".join(unknown))
        print("  Nothing in the app maps to these; they are dead weight and may")
        print("  indicate a ticker rename that left the old node behind.")

    if args.json:
        json.dump({t: dict(v) for t, v in report.items()}, open(args.json, "w"), indent=1)
        print(f"\nFull report written to {args.json}")

    print("\nRead-only — nothing was modified.")


if __name__ == "__main__":
    main()
