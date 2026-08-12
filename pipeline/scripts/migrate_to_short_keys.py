# pipeline/scripts/migrate_to_short_keys.py
"""
Idempotent migration: enforces the `short` primary key across every
Firestore collection that stores per-company data.

Handled collections:
  * companies/{short}   — merges price/metadata from any old "SCOM_NR"
    doc, deletes subcollections (snapshots, technicals) at the old key.
  * financials/{short}  — merges annual[], dividends[], corporate_actions[],
    announcements[] arrays from any "SCOM.NR" or "SCOM_NR" doc.
  * fundamentals/{short} — merges shares_outstanding_mn + related fields
    from wrong-key docs.

For each collection + company the script tries three candidate old-key
forms (short, ticker with dots, ticker with underscores) and picks the
newest / most-populated. Safe to re-run — a company whose data is already
at the short key is a no-op.

Usage:
    python pipeline/scripts/migrate_to_short_keys.py            # writes
    python pipeline/scripts/migrate_to_short_keys.py --dry-run  # audits only

Env:
    FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import argparse
import logging
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies
from scripts.push_to_firestore import get_db
from src.identity import doc_id_for

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUBCOLLECTIONS = ("snapshots", "technicals")


def _candidate_old_ids(company: dict) -> list[str]:
    """
    Every historically-observed doc-id form for a company that is NOT the
    canonical short form. Used to scan for legacy docs during migration.
    """
    short = doc_id_for(company)
    ticker = company.get("ticker", "")
    candidates = {
        ticker,                       # "SCOM.NR"
        ticker.replace(".", "_"),    # "SCOM_NR"
        ticker.upper(),
        ticker.replace(".", "_").upper(),
    }
    candidates.discard(short)
    candidates.discard("")
    return sorted(candidates)


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


def migrate_company(db, company: dict, dry_run: bool = False) -> dict:
    old_id = company["ticker"].replace(".", "_")   # e.g. SCOM_NR
    new_id = doc_id_for(company)                    # e.g. SCOM

    if old_id == new_id:
        log.info("%-20s  companies: no-op (old == new key)", new_id)
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

    if dry_run:
        log.info("%-20s  companies: would migrate (old exists=%s, new exists=%s)",
                 new_id, old_snap.exists, new_snap.exists)
        return {"ticker": new_id, "migrated": True, "dry_run": True}

    # Write the new document
    new_ref.set(meta)

    # Delete old document (subcollections first)
    if old_snap.exists:
        _delete_subcollections(db, old_id)
        old_ref.delete()
        log.info("%-20s  companies: deleted old doc %s", new_id, old_id)

    return {"ticker": new_id, "migrated": True}


# ── Generic collection migration for financials / fundamentals ──────────────

def _merge_arrays(target: dict, incoming: dict, keys: tuple[str, ...]) -> int:
    """
    For each field in `keys`, extend target[field] with incoming[field] rows
    that aren't already present. Simple dedup by (period+period_end),
    (announcement_date+ex_date+amount_kes), or (date+title) depending on
    the field. Returns count of rows added.
    """
    added = 0
    dedup_keys = {
        "annual":            lambda r: (r.get("period"), r.get("period_end")),
        "dividends":         lambda r: (r.get("announcement_date"), r.get("ex_date"), r.get("amount_kes")),
        "corporate_actions": lambda r: (r.get("date"), (r.get("title") or r.get("details") or "")[:50]),
        "announcements":     lambda r: (r.get("date"), r.get("title", "")[:50], r.get("url", "")),
    }
    for field in keys:
        if field not in incoming or not isinstance(incoming[field], list):
            continue
        existing = target.get(field) or []
        keyfn = dedup_keys.get(field, lambda r: str(r))
        seen = {keyfn(r) for r in existing}
        for row in incoming[field]:
            if keyfn(row) not in seen:
                existing.append(row)
                seen.add(keyfn(row))
                added += 1
        target[field] = existing
    return added


def migrate_generic_collection(
    db,
    collection_name: str,
    company: dict,
    array_fields: tuple[str, ...],
    dry_run: bool = False,
) -> dict:
    """
    Merge any legacy-keyed docs in `collection_name` for `company` into the
    short-form doc. `array_fields` is the list of top-level keys that hold
    per-record arrays that need dedup-merge (e.g. dividends, annual).

    Non-array fields (like fundamentals.shares_outstanding_mn) are preserved
    from whichever doc has them — short-form doc wins on conflict, since a
    manual seed or later pipeline run is more trustworthy than an older
    legacy write.
    """
    new_id = doc_id_for(company)
    new_ref = db.collection(collection_name).document(new_id)
    new_snap = new_ref.get()
    new_data = new_snap.to_dict() if new_snap.exists else {}

    old_ids = _candidate_old_ids(company)
    old_docs = []
    for oid in old_ids:
        snap = db.collection(collection_name).document(oid).get()
        if snap.exists:
            old_docs.append((oid, snap))

    if not old_docs:
        return {"ticker": new_id, "collection": collection_name, "migrated": False, "reason": "no_legacy_doc"}

    # Merge old docs into new_data
    merged = dict(new_data)
    added_total = 0
    for oid, snap in old_docs:
        data = snap.to_dict() or {}
        added_total += _merge_arrays(merged, data, array_fields)
        # Backfill any top-level scalars new_data is missing
        for k, v in data.items():
            if k in array_fields:
                continue
            if k not in merged or merged.get(k) in (None, "", 0):
                merged[k] = v

    if dry_run:
        log.info("%-20s  %s: would merge from %s (+%d rows)",
                 new_id, collection_name, [o for o, _ in old_docs], added_total)
        return {"ticker": new_id, "collection": collection_name, "migrated": True, "dry_run": True}

    if added_total > 0 or any(k for k in merged if k not in new_data):
        new_ref.set(merged, merge=True)
        log.info("%-20s  %s: merged %d rows from %s",
                 new_id, collection_name, added_total, [o for o, _ in old_docs])

    for oid, _ in old_docs:
        db.collection(collection_name).document(oid).delete()
        log.info("%-20s  %s: deleted legacy doc %s", new_id, collection_name, oid)

    return {
        "ticker": new_id,
        "collection": collection_name,
        "migrated": True,
        "rows_merged": added_total,
        "legacy_docs_deleted": len(old_docs),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate Firestore docs to short keys")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report actions without writing/deleting")
    args = parser.parse_args()

    db = get_db()
    companies = load_companies()

    label = "DRY-RUN" if args.dry_run else "LIVE"
    log.info("=== [%s] Migrating %d companies to short-key format ===",
             label, len(companies))

    stats = {"companies": 0, "financials": 0, "fundamentals": 0}
    for company in companies:
        try:
            if migrate_company(db, company, args.dry_run).get("migrated"):
                stats["companies"] += 1
        except Exception as exc:
            log.error("Error migrating companies/%s: %s",
                      company.get("short", "?"), exc, exc_info=True)

        try:
            r = migrate_generic_collection(
                db, "financials", company,
                array_fields=("annual", "dividends", "corporate_actions", "announcements"),
                dry_run=args.dry_run,
            )
            if r.get("migrated"):
                stats["financials"] += 1
        except Exception as exc:
            log.error("Error migrating financials/%s: %s",
                      company.get("short", "?"), exc, exc_info=True)

        try:
            r = migrate_generic_collection(
                db, "fundamentals", company,
                array_fields=("estimates",),
                dry_run=args.dry_run,
            )
            if r.get("migrated"):
                stats["fundamentals"] += 1
        except Exception as exc:
            log.error("Error migrating fundamentals/%s: %s",
                      company.get("short", "?"), exc, exc_info=True)

    log.info("=== [%s] Done. companies=%d financials=%d fundamentals=%d ===",
             label, stats["companies"], stats["financials"], stats["fundamentals"])


if __name__ == "__main__":
    main()
