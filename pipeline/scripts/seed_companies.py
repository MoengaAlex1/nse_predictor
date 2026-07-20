# pipeline/scripts/seed_companies.py
"""
Run once: populates companies/{ticker} documents in Firestore.
Usage: python pipeline/scripts/seed_companies.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
from pathlib import Path
from typing import Any

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies
from scripts.push_to_firestore import get_db


def seed_company(db: Any, company: dict) -> None:
    safe = company["ticker"].replace(".", "_")
    doc = {
        "name":             company["name"],
        "short":            company["short"],
        "sector":           company["sector"],
        "color":            company["color"],
        "icon":             company["icon"],
        "ticker":           company["ticker"],
        "csv":              company["csv"],
        "description":      company.get("description", ""),
        "current_price":    None,
        "change_pct_today": None,
        "signal":           None,
        "price_preview":    [],
        "last_updated":     None,
    }
    db.collection("companies").document(safe).set(doc, merge=True)
    print(f"  Seeded: {safe}")


def main() -> None:
    db = get_db()
    companies = load_companies()
    for company in companies:
        seed_company(db, company)
    print(f"\nDone — {len(companies)} companies seeded.")


if __name__ == "__main__":
    main()
