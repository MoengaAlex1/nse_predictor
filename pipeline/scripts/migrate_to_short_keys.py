# pipeline/scripts/migrate_to_short_keys.py
"""
One-shot migration: moves Firestore company documents from the old
{TICKER_NR} key format to the new {short} key format (e.g. SCOM_NR → SCOM).

For each company:
  1. Create/update companies/{short} with full metadata from companies.json.
  2. Copy price_history, price_preview, current_price, change_pct_today,
     last_updated from the old companies/{TICKER_NR} doc (if it exists and
     has more/newer data than the new doc already has).
  3. Delete the old companies/{TICKER_NR} document and its subcollections
     (snapshots, technicals).

Usage:
    python pipeline/scripts/migrate_to_short_keys.py
Env:
    FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import logging
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies
from scripts.push_to_firestore import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUBCOLLECTIONS = ("snapshots", "technicals")


def _delete_subcollections(db, doc_id: str) -> None:
    for sub in SUBCOLLECTIONS:
        col_ref = db.collection("companies").document(doc_id).collection(sub)
        docs = list(col_ref.stream())
        for d in docs:
            d.reference.delete()
        if docs:
            log.info("  deleted %d %s docs from %s", len(docs), sub, doc_id)


def _is_newer_or_larger(old_data: dict, new_data: dict | None) -> bool:
    """Return True if old_data has more price_history entries than new_data."""
    old_pts = len(old_data.get("price_history") or [])
    new_pts = len((new_data or {}).get("price_history") or [])
    return old_pts > new_pts


def migrate_company(db, company: dict) -> dict:
    old_id = company["ticker"].replace(".", "_")   # e.g. SCOM_NR
    new_id = company["short"]                       # e.g. SCOM

    if old_id == new_id:
        log.info("%-20s  no-op (old == new key)", new_id)
        return {"ticker": new_id, "migrated": False, "reason": "same_key"}

    old_ref = db.collection("companies").document(old_id)
    new_ref = db.collection("companies").document(new_id)

    old_snap = old_ref.get()
    new_snap = new_ref.get()

    old_data = old_snap.to_dict() if old_snap.exists else None
    new_data = new_snap.to_dict() if new_snap.exists else None

    # Build the full metadata doc from companies.json
    meta = {
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

    # Merge price fields: prefer whichever source has more price_history points
    if old_data and _is_newer_or_larger(old_data, new_data):
        for field in ("current_price", "change_pct_today", "price_history",
                      "price_preview", "last_updated", "signal"):
            if field in old_data:
                meta[field] = old_data[field]
        log.info("%-20s  using old doc (%d pts)", new_id,
                 len(old_data.get("price_history") or []))
    elif new_data:
        for field in ("current_price", "change_pct_today", "price_history",
                      "price_preview", "last_updated", "signal"):
            if field in new_data:
                meta[field] = new_data[field]
        log.info("%-20s  using new doc (%d pts)", new_id,
                 len(new_data.get("price_history") or []))
    else:
        log.info("%-20s  no price data yet — seeding metadata only", new_id)

    # Write the new document
    new_ref.set(meta)

    # Delete old document (subcollections first)
    if old_snap.exists:
        _delete_subcollections(db, old_id)
        old_ref.delete()
        log.info("%-20s  deleted old doc %s", new_id, old_id)

    return {"ticker": new_id, "migrated": True}


def main() -> None:
    db = get_db()
    companies = load_companies()

    log.info("=== Migrating %d companies to short-key format ===", len(companies))

    done = 0
    for company in companies:
        try:
            result = migrate_company(db, company)
            if result["migrated"]:
                done += 1
        except Exception as exc:
            log.error("Error migrating %s: %s", company.get("short", "?"), exc, exc_info=True)

    log.info("Migration complete: %d/%d companies migrated.", done, len(companies))


if __name__ == "__main__":
    main()
