"""
Seed fallback last-known prices from the NSE daily-share-movements Excel
(pipeline/data/last_vwap_2023.json — extracted from the September 2023
VWAP sheet, the latest available in the source workbook).

Purpose: many small-cap NSE tickers don't have current RTDB prices
(their intraday feed is thin or absent), which means the screener's
Market Cap column shows "—" even for tickers where we have shares
outstanding. Writing a last_known_price + as_of date lets the frontend
compute Market Cap = last_known_price × shares_outstanding as an
honest fallback, clearly labelled by the as-of date.

Writes to companies/{ticker}:
  last_known_price       (number, KES)
  last_known_price_as_of (YYYY-MM-DD)
  last_known_price_source (string, e.g. "NSE-daily-share-movements-excel")

Never overwrites current_price — that stays as the RTDB-fed live price.

Usage: python pipeline/scripts/seed_last_vwap.py [--dry-run]
Env:   FIREBASE_SERVICE_ACCOUNT_JSON
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

DATA_FILE = PIPELINE_ROOT / "config" / "last_vwap_2023.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not DATA_FILE.exists():
        raise SystemExit(f"Missing {DATA_FILE}")

    with open(DATA_FILE, encoding="utf-8") as fh:
        payload = json.load(fh)

    as_of = payload.get("as_of", "unknown")
    source = payload.get("source", "excel")
    prices: dict[str, float] = payload.get("prices", {})

    print(f"Seeding last_known_price for {len(prices)} tickers  (as_of={as_of})")

    from scripts.firebase_client import get_firestore
    db = get_firestore()

    updated = 0
    for tkr, price in sorted(prices.items()):
        update = {
            "last_known_price":        price,
            "last_known_price_as_of":  as_of,
            "last_known_price_source": source,
        }
        print(f"  {tkr:6}  KES {price:>10,.2f}")
        if not args.dry_run:
            db.collection("companies").document(tkr).set(update, merge=True)
        updated += 1

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n=== Done === {verb} last_known_price for {updated} tickers")


if __name__ == "__main__":
    main()
