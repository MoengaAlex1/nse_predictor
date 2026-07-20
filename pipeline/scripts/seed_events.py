# pipeline/scripts/seed_events.py
"""
Run once: populates events/{ticker} documents in Firestore from corporate_events.json.
Usage: python pipeline/scripts/seed_events.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import json
import sys
from pathlib import Path
from typing import Any

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.push_to_firestore import get_db

EVENTS_CONFIG = PIPELINE_ROOT / "config" / "corporate_events.json"


def seed_events(db: Any) -> None:
    with open(EVENTS_CONFIG, encoding="utf-8") as f:
        all_events: dict = json.load(f)

    for safe_ticker, payload in all_events.items():
        items = payload.get("items", [])
        # Sort by date ascending so newest events appear last in the list
        items_sorted = sorted(items, key=lambda e: e["date"])
        db.collection("events").document(safe_ticker).set(
            {"items": items_sorted}, merge=False
        )
        print(f"  Seeded {len(items_sorted)} events for {safe_ticker}")

    print(f"\nDone — {len(all_events)} tickers seeded.")


def main() -> None:
    db = get_db()
    seed_events(db)


if __name__ == "__main__":
    main()
