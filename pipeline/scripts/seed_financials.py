"""
Seed financials/{short} documents in Firestore from financials.json.

Note: financials.json historically uses "SCOM_NR" safe-form keys, but the
Firestore doc-id is always the short form ("SCOM"). We normalize the key
via src.identity.short_from_display_ticker() at seed time so the JSON
itself doesn't need a bulk rewrite.

Usage: python pipeline/scripts/seed_financials.py
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
from src.identity import short_from_display_ticker, is_short

FINANCIALS_CONFIG = PIPELINE_ROOT / "config" / "financials.json"


def seed_financials(db: Any) -> None:
    with open(FINANCIALS_CONFIG, encoding="utf-8") as f:
        all_financials: dict = json.load(f)

    for json_key, payload in all_financials.items():
        # Normalize "SCOM_NR" → "SCOM" (short form). No-op if already short.
        short = json_key if is_short(json_key) else short_from_display_ticker(json_key)

        annual = payload.get("annual", [])
        annual_sorted = sorted(annual, key=lambda r: r["period_end"])
        payload["annual"] = annual_sorted

        divs = payload.get("dividends", [])
        divs_sorted = sorted(divs, key=lambda d: d["announcement_date"])
        payload["dividends"] = divs_sorted

        db.collection("financials").document(short).set(payload, merge=False)
        print(
            f"  {short:<8} (from {json_key}): {len(annual_sorted)} results, "
            f"{len(divs_sorted)} dividends, "
            f"{len(payload.get('corporate_actions', []))} actions"
        )

    print(f"\nDone — {len(all_financials)} tickers seeded (short-key normalized).")


def main() -> None:
    db = get_db()
    seed_financials(db)


if __name__ == "__main__":
    main()
