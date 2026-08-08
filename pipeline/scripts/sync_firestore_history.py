"""
sync_firestore_history.py

Rebuilds the Firestore price history for a company from the RTDB series.

WHY BOTH STORES NEED FIXING
---------------------------
The web app reads prices from two places:

  RTDB      prices/{TICKER}/{DATE}          -> the price history chart
  Firestore companies/{TICKER}.price_history -> 52-week range, all-time high and
                                                low, the performance tiles and
                                                the investment calculator

Correcting RTDB alone therefore only half fixes the page. After the SMER
decimal repair the chart was right while Firestore still held 161 entries below
KES 1.00, so the company page kept reporting an all-time low of 0.15.

RTDB is the system of record for OHLCV, so this derives Firestore from it
rather than recomputing prices a second way. Full history is carried across —
SMER starts 2007-01-02.

WHAT IT WRITES
  price_history   [{date, price}] for every RTDB day with a close
  price_preview   the last 30 closes, which the sparkline uses
  current_price   the most recent close
  price_date      the date of that close

Nothing else on the document is touched, so signals, snapshots, technicals and
predictions are left exactly as they are.

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

PREVIEW_POINTS = 30


def build_history(node: dict) -> list[dict]:
    """[{date, price}] from an RTDB ticker node, oldest first."""
    out = []
    for date, row in sorted(node.items()):
        if not isinstance(row, dict):
            continue
        close = row.get("c")
        if isinstance(close, (int, float)) and close > 0:
            out.append({"date": date, "price": round(float(close), 4)})
    return out


def build_update(node: dict) -> dict | None:
    history = build_history(node)
    if not history:
        return None
    return {
        "price_history": history,
        "price_preview": [p["price"] for p in history[-PREVIEW_POINTS:]],
        "current_price": history[-1]["price"],
        "price_date": history[-1]["date"],
    }


def compare(existing: list[dict] | None, rebuilt: list[dict]) -> dict:
    """Summarise what would change, so a dry run is meaningful."""
    existing = existing or []
    old = {p.get("date"): p.get("price") for p in existing if isinstance(p, dict)}
    new = {p["date"]: p["price"] for p in rebuilt}
    changed = [d for d in new if d in old and old[d] != new[d]]
    return {
        "before_points": len(old),
        "after_points": len(new),
        "added": len(set(new) - set(old)),
        "removed": len(set(old) - set(new)),
        "changed": len(changed),
        "sample": [(d, old[d], new[d]) for d in sorted(changed)[:8]],
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", action="append", required=True,
                    help="Ticker to sync (repeatable)")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from pipeline.scripts.firebase_client import get_rtdb
    from pipeline.scripts.push_to_firestore import get_db, update_company_public

    root = get_rtdb()
    db = get_db()

    for ticker in args.ticker:
        node = root.child(f"prices/{ticker}").get()
        if not node:
            log.warning("%s: no RTDB history, skipping", ticker)
            continue

        update = build_update(node)
        if not update:
            log.warning("%s: no usable closes, skipping", ticker)
            continue

        snap = db.collection("companies").document(ticker).get()
        existing = (snap.to_dict() or {}).get("price_history") if snap.exists else None
        diff = compare(existing, update["price_history"])

        print(f"\n{ticker}")
        print(f"  points   {diff['before_points']} -> {diff['after_points']}"
              f"   (+{diff['added']} -{diff['removed']}, {diff['changed']} changed)")
        print(f"  range    {update['price_history'][0]['date']} .. {update['price_date']}")
        print(f"  current  {update['current_price']}")
        below = [p for p in update["price_history"] if p["price"] < 1.0]
        print(f"  entries below KES 1.00 after sync: {len(below)}")
        for d, o, n in diff["sample"]:
            print(f"    {d}  {o} -> {n}")

        if args.apply:
            update_company_public(db, ticker, update)
            print(f"  WRITTEN to companies/{ticker}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Pass --apply to write.")


if __name__ == "__main__":
    main()
