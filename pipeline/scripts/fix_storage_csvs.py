"""
fix_storage_csvs.py

Downloads cleaned CSVs from Firebase Storage, applies decimal-error corrections
(via fix_csv_price_errors.py logic), re-uploads fixed CSVs, and pushes updated
price_history / current_price to Firestore.

Usage:
    python pipeline/scripts/fix_storage_csvs.py --tickers EQTY_NR KCB_NR OCH_NR TRFC_NR
    python pipeline/scripts/fix_storage_csvs.py --all
    python pipeline/scripts/fix_storage_csvs.py --dry-run --tickers EQTY_NR
    python pipeline/scripts/fix_storage_csvs.py --force-push --tickers NSE_NR SCOM_NR

    --force-push: skip decimal-fix step; just download from Storage and push to Firestore.
                  Use after a backfill scrape to sync the updated CSV to Firestore without
                  re-running the decimal correction logic.

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.push_to_firestore import (
    get_db,
    download_model_from_storage,
    upload_model_to_storage,
    update_company_public,
)
from scripts.fix_csv_price_errors import fix_ticker
from config import load_companies, DATA_CLEANED

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()


def _build_firestore_payload(csv_path: Path) -> dict | None:
    """Read fixed CSV and build the Firestore update payload."""
    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None or "Close" not in df.columns:
            return None
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=False, format="mixed")
        df = df.set_index(date_col).sort_index()
        df.index.name = "Date"

        if "Is_Stale" in df.columns:
            df = df[df["Is_Stale"] != 1]
        today_ts = pd.Timestamp(TODAY)
        df = df[df.index <= today_ts]
        df = df[df.index.dayofweek < 5]
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = df.dropna(subset=["Close"])

        if df.empty:
            return None

        price_history = [
            {"date": idx.strftime("%Y-%m-%d"), "price": round(float(val), 4)}
            for idx, val in df["Close"].items()
            if not pd.isna(val)
        ]
        if not price_history:
            return None

        current_price = round(float(df["Close"].iloc[-1]), 4)
        closes = df["Close"].dropna()
        if len(closes) >= 2:
            prev = float(closes.iloc[-2])
            change_pct = float((current_price - prev) / prev * 100) if prev > 0 else 0.0
            change_pct = max(-15.0, min(15.0, change_pct))
        else:
            change_pct = 0.0

        return {
            "current_price":    current_price,
            "change_pct_today": round(change_pct, 4),
            "price_history":    price_history,
            "price_preview":    [p["price"] for p in price_history[-30:]],
            "last_updated":     TODAY,
        }
    except Exception as exc:
        log.error("Error building Firestore payload: %s", exc)
        return None


def fix_and_push(
    company: dict,
    db,
    dry_run: bool = False,
    force_push: bool = False,
    from_git: bool = False,
) -> dict:
    """Download from Storage, fix decimal errors, re-upload, and push to Firestore.

    When force_push=True the decimal-fix step is skipped and the CSV is pushed
    to Firestore as-is.  Use this after a backfill scrape has already updated
    the Storage CSV with the correct data.

    When from_git=True the Storage download step is skipped entirely and the
    git-checked-out file in data/cleaned/ is used directly.  This lets CI push
    already-corrected CSVs (committed to git) to Storage + Firestore without
    needing those files to exist in Storage first.
    """
    safe = company["ticker"].replace(".", "_")
    doc_id = company["short"]
    storage_path = f"data/cleaned/{safe}_cleaned.csv"
    local_path = DATA_CLEANED / f"{safe}_cleaned.csv"

    DATA_CLEANED.mkdir(parents=True, exist_ok=True)

    if from_git:
        if not local_path.exists():
            log.warning("%s: not found in git checkout (%s) — skipping", safe, local_path)
            return {"ticker": safe, "fixed": 0, "status": "not_found_local"}
        if dry_run:
            log.info("%s: --from-git --dry-run — would upload git CSV to Storage + Firestore", safe)
            return {"ticker": safe, "fixed": 0, "status": "dry_run_from_git"}
        upload_model_to_storage(str(local_path), storage_path)
        log.info("%s: git CSV uploaded to Storage", safe)
        payload = _build_firestore_payload(local_path)
        if payload:
            update_company_public(db, doc_id, payload)
            log.info(
                "%s: Firestore seeded from git CSV — price_history=%d pts, current_price=%.4f",
                safe, len(payload["price_history"]), payload["current_price"],
            )
            return {"ticker": safe, "fixed": len(payload["price_history"]),
                    "status": "seeded_from_git", "rows": len(payload["price_history"])}
        log.warning("%s: could not build Firestore payload from git CSV", safe)
        return {"ticker": safe, "fixed": 0, "status": "no_payload"}

    ok = download_model_from_storage(storage_path, str(local_path))
    if not ok:
        log.warning("%s: not found in Firebase Storage — skipping", safe)
        return {"ticker": safe, "fixed": 0, "status": "not_found"}

    if force_push:
        if dry_run:
            log.info("%s: --force-push --dry-run — would push from Storage CSV to Firestore", safe)
            return {"ticker": safe, "fixed": 0, "status": "dry_run_force_push"}
        payload = _build_firestore_payload(local_path)
        if payload:
            update_company_public(db, doc_id, payload)
            log.info(
                "%s: force-pushed to Firestore — price_history=%d pts, current_price=%.4f",
                safe, len(payload["price_history"]), payload["current_price"],
            )
            return {"ticker": safe, "fixed": 0, "status": "force_pushed",
                    "rows": len(payload["price_history"])}
        log.warning("%s: could not build Firestore payload", safe)
        return {"ticker": safe, "fixed": 0, "status": "no_payload"}

    result = fix_ticker(local_path, dry_run=dry_run)

    if result.get("fixed", 0) > 0 and not dry_run:
        upload_model_to_storage(str(local_path), storage_path)
        log.info("%s: fixed CSV re-uploaded to Storage", safe)

        payload = _build_firestore_payload(local_path)
        if payload:
            update_company_public(db, doc_id, payload)
            log.info(
                "%s: Firestore updated — price_history=%d pts, current_price=%.4f",
                safe, len(payload["price_history"]), payload["current_price"],
            )
        else:
            log.warning("%s: could not build Firestore payload after fix", safe)

    return result


def main(
    dry_run: bool = False,
    tickers: list[str] | None = None,
    all_: bool = False,
    force_push: bool = False,
    from_git: bool = False,
) -> None:
    companies = load_companies()
    safe_map = {c["ticker"].replace(".", "_"): c for c in companies}

    if tickers:
        targets = [safe_map[t] for t in tickers if t in safe_map]
        missing = [t for t in tickers if t not in safe_map]
        if missing:
            log.warning("Unknown tickers (skipped): %s", ", ".join(missing))
        if not targets:
            log.error("No valid tickers found")
            return
    elif all_:
        targets = companies
    else:
        log.error("Specify --tickers SAFE_NAME... or --all")
        return

    db = get_db()
    if from_git:
        mode = "seed-from-git"
    elif force_push:
        mode = "FORCE-PUSH"
    else:
        mode = "fix + push"
    log.info(
        "=== CSV %s | %d companies%s ===",
        mode, len(targets), " [DRY RUN]" if dry_run else "",
    )

    results = []
    for company in targets:
        result = fix_and_push(
            company, db, dry_run=dry_run, force_push=force_push, from_git=from_git
        )
        results.append(result)

    if from_git:
        seeded = [r for r in results if r.get("status") == "seeded_from_git"]
        print()
        print(f"Seeded from git: {len(seeded)}/{len(results)} tickers")
        for r in seeded:
            print(f"  {r['ticker']}: {r.get('rows', '?')} price points")
    elif force_push:
        pushed = [r for r in results if r.get("status") in ("force_pushed",)]
        print()
        print(f"Force-pushed: {len(pushed)}/{len(results)} tickers")
        for r in pushed:
            print(f"  {r['ticker']}: {r.get('rows', '?')} price points")
    else:
        changed = [r for r in results if r.get("fixed", 0) > 0]
        print()
        print(f"Fixed: {len(changed)}/{len(results)} tickers")
        for r in changed:
            before = r.get("rows_before", 0)
            after = r.get("rows_after", before)
            print(f"  {r['ticker']}: {r['fixed']} correction(s)  ({before} → {after} rows)")
    if dry_run:
        print("(DRY RUN — no files written)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fix CSV decimal errors in Firebase Storage and push to Firestore"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only — no writes")
    parser.add_argument("--tickers", nargs="+", help="Safe ticker names e.g. EQTY_NR KCB_NR")
    parser.add_argument("--all", dest="all_", action="store_true", help="Process all companies")
    parser.add_argument(
        "--force-push",
        action="store_true",
        help="Skip decimal fix; push current Storage CSV to Firestore as-is (use after backfill)",
    )
    parser.add_argument(
        "--from-git",
        action="store_true",
        help=(
            "Skip Storage download; upload git-checked-out data/cleaned/ CSV to Storage "
            "and seed Firestore. Use when the corrected CSV is committed but not yet in Storage."
        ),
    )
    args = parser.parse_args()
    main(
        dry_run=args.dry_run,
        tickers=args.tickers,
        all_=args.all_,
        force_push=args.force_push,
        from_git=args.from_git,
    )
