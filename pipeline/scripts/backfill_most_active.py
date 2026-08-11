"""
Backfill market_overview/{date}.most_active from the technicals subcollections.

The main daily pipeline (run_inference.py) started writing most_active
after 2026-08-11. Older market_overview docs pre-date that field, so
their Home-page "Most Active" box falls back to |Δ|-sort which shows
small illiquid tickers.

This script backfills any existing market_overview doc by:
 1. Reading the latest technicals doc for every ticker in companies/.
 2. Sorting by the day's volume, top 5.
 3. Computing turnover_kes = volume × current_price.
 4. Writing most_active[] into the target market_overview doc (default:
    the newest one).

Usage:  python pipeline/scripts/backfill_most_active.py [--date YYYY-MM-DD] [--dry-run]
Env:    FIREBASE_SERVICE_ACCOUNT_JSON
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None,
                        help="market_overview doc id to backfill (default: newest)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from scripts.firebase_client import get_firestore
    db = get_firestore()

    # Pick target market_overview doc
    if args.date:
        target_id = args.date
    else:
        overviews = list(db.collection("market_overview").stream())
        overviews.sort(key=lambda d: d.id, reverse=True)
        if not overviews:
            raise SystemExit("No market_overview docs found")
        target_id = overviews[0].id
    print(f"Target: market_overview/{target_id}")

    # For each company, read the latest technicals doc + current price
    rows: list[tuple[str, int, float, float]] = []
    companies = list(db.collection("companies").stream())
    print(f"Scanning {len(companies)} companies for latest technicals...")

    for c in companies:
        cd = c.to_dict() or {}
        price = cd.get("current_price")
        change_pct = cd.get("change_pct_today") or 0.0
        if price is None or price <= 0:
            continue
        # Pull the newest technicals doc — order by date desc, limit 1
        tech_docs = list(
            db.collection("companies").document(c.id).collection("technicals")
              .order_by("date", direction="DESCENDING").limit(1).stream()
        )
        if not tech_docs:
            continue
        td = tech_docs[0].to_dict() or {}
        vol = td.get("volume")
        if not isinstance(vol, (int, float)) or vol <= 0:
            continue
        rows.append((c.id, int(vol), float(price), float(change_pct)))

    if not rows:
        raise SystemExit("No tickers had usable volume — check technicals data")

    rows.sort(key=lambda r: r[1], reverse=True)
    most_active = [
        {
            "ticker":       t,
            "volume":       v,
            "turnover_kes": round(v * p, 2),
            "change_pct":   round(cp, 2),
        }
        for t, v, p, cp in rows[:5]
    ]

    print("\n=== Most Active by volume ===")
    for r in most_active:
        print(f"  {r['ticker']:6}  vol={r['volume']:>12,}  turnover=KES {r['turnover_kes']:>14,.0f}  Δ={r['change_pct']:+.2f}%")

    if args.dry_run:
        print("\n(dry-run — not writing)")
        return

    db.collection("market_overview").document(target_id).set(
        {"most_active": most_active}, merge=True
    )
    print(f"\nWrote most_active[] into market_overview/{target_id}")


if __name__ == "__main__":
    main()
