"""
fix_storage_csvs.py

Downloads cleaned CSVs from Firebase Storage, applies decimal-error corrections
(via fix_csv_price_errors.py logic), re-uploads fixed CSVs, and pushes updated
price_history / current_price to Firestore.

Usage:
    python pipeline/scripts/fix_storage_csvs.py --tickers EQTY_NR KCB_NR OCH_NR TRFC_NR
    python pipeline/scripts/fix_storage_csvs.py --all
    python pipeline/scripts/fix_storage_csvs.py --dry-run --tickers EQTY_NR

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


def fix_and_push(company: dict, db, dry_run: bool = False) -> dict:
    """Download from Storage, fix decimal errors, re-upload, and push to Firestore."""
    safe = company["ticker"].replace(".", "_")
    doc_id = company["short"]
    storage_path = f"data/cleaned/{safe}_cleaned.csv"
    local_path = DATA_CLEANED / f"{safe}_cleaned.csv"

    DATA_CLEANED.mkdir(parents=True, exist_ok=True)

    ok = download_model_from_storage(storage_path, str(local_path))
    if not ok:
        log.warning("%s: not found in Firebase Storage — skipping", safe)
        return {"ticker": safe, "fixed": 0, "status": "not_found"}

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


def main(dry_run: bool = False, tickers: list[str] | None = None, all_: bool = False) -> None:
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
    log.info(
        "=== CSV fix + push | %d companies%s ===",
        len(targets), " [DRY RUN]" if dry_run else "",
    )

    results = []
    for company in targets:
        result = fix_and_push(company, db, dry_run=dry_run)
        results.append(result)

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
    args = parser.parse_args()
    main(dry_run=args.dry_run, tickers=args.tickers, all_=args.all_)
