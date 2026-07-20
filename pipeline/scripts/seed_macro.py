"""
Seed macro/kenya document in Firestore from macro_kenya.json.
Usage: python pipeline/scripts/seed_macro.py
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

MACRO_CONFIG = PIPELINE_ROOT / "config" / "macro_kenya.json"


def seed_macro(db: Any) -> None:
    with open(MACRO_CONFIG, encoding="utf-8") as f:
        macro: dict = json.load(f)

    cbk = macro.get("cbk_rates", [])
    cbk_sorted = sorted(cbk, key=lambda r: r["date"])
    macro["cbk_rates"] = cbk_sorted

    db.collection("macro").document("kenya").set(macro, merge=False)
    print(f"  CBK rate decisions: {len(cbk_sorted)}")
    print(f"  Inflation years: {len(macro.get('annual_inflation', {}))}")
    print(f"  KES/USD years: {len(macro.get('kes_usd_year_end', {}))}")
    print(f"  NSE20 years: {len(macro.get('nse20_year_end', {}))}")
    print(f"  Macro events: {len(macro.get('macro_events', []))}")
    print("\nDone — macro/kenya seeded.")


def main() -> None:
    db = get_db()
    seed_macro(db)


if __name__ == "__main__":
    main()
