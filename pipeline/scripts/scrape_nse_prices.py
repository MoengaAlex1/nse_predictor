# pipeline/scripts/scrape_nse_prices.py
"""
Daily NSE price scraper.

For each company:
  1. Download the existing cleaned CSV from Firebase Storage into CSVS_TMP.
     If it is not in Storage yet, seed from the repo's data/cleaned/ directory.
  2. Fetch the latest OHLCV row via yfinance (.KE ticker).
  3. Append any new rows, save locally, and re-upload to Firebase Storage.

The function ``main()`` is called by run_daily_update.py and returns a dict
keyed by safe ticker name.

Usage: python pipeline/scripts/scrape_nse_prices.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import logging
import os
from datetime import date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import yfinance as yf

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.push_to_firestore import (
    get_db,
    download_model_from_storage,
    upload_model_to_storage,
)
from config import load_companies

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()
CSVS_TMP = Path("/tmp/nse_csvs")

# Columns produced by the cleaning pipeline; must exist in every CSV.
_REQUIRED_COLS = {"Open", "High", "Low", "Close", "Volume"}


def _safe_name(ticker: str) -> str:
    """Convert a company ticker to its safe filesystem name (dots → underscores)."""
    return ticker.replace(".", "_")


def _yf_ticker(safe: str) -> str:
    """
    Convert a safe ticker name to a Yahoo Finance .KE ticker.

    Examples:
      SCOM_NR  → SCOM.KE
      EQTY_NR  → EQTY.KE
      ABSA_NR  → ABSA.KE
    """
    base = safe
    if base.endswith("_NR"):
        base = base[:-3]
    return f"{base}.KE"


def _load_local_csv(path: Path) -> pd.DataFrame | None:
    """Load a CSV with a DatetimeIndex. Returns None on any error."""
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            log.warning("No date column in %s", path.name)
            return None
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, format="mixed")
        df = df.set_index(date_col)
        df.index.name = "Date"
        df = df.sort_index()
        return df
    except Exception as exc:
        log.warning("Could not load CSV %s: %s", path, exc)
        return None


def scrape_company(company: dict) -> dict:
    """
    Download, update, and re-upload the cleaned CSV for one company.

    Returns a result dict:
      {"ticker": safe, "scraped": bool, "date": str, "close": float | None}
    """
    ticker = company["ticker"]
    safe = _safe_name(ticker)
    storage_path = f"data/cleaned/{safe}_cleaned.csv"
    local_path = CSVS_TMP / f"{safe}_cleaned.csv"

    result: dict[str, Any] = {
        "ticker": safe,
        "scraped": False,
        "date": TODAY,
        "close": None,
    }

    # ── 1. Obtain the latest CSV ──────────────────────────────────────────────
    in_storage = download_model_from_storage(storage_path, str(local_path))

    if not in_storage:
        # Seed from the repo's cleaned CSV if it exists
        repo_csv = PIPELINE_ROOT.parent / "data" / "cleaned" / f"{safe}_cleaned.csv"
        if repo_csv.exists():
            import shutil
            CSVS_TMP.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_csv, local_path)
            log.info("%s: seeded from repo cleaned CSV", safe)
        else:
            log.warning("%s: no CSV in Storage or repo — starting from scratch", safe)

    # ── 2. Load existing data ─────────────────────────────────────────────────
    existing_df: pd.DataFrame | None = None
    if local_path.exists():
        existing_df = _load_local_csv(local_path)

    # ── 3. Fetch from Yahoo Finance ───────────────────────────────────────────
    yf_sym = _yf_ticker(safe)
    try:
        raw = yf.download(yf_sym, period="5d", auto_adjust=True, progress=False)
        if raw.empty:
            log.warning("%s: yfinance returned empty data for %s", safe, yf_sym)
            return result

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        raw.index = pd.to_datetime(raw.index)
        raw.index.name = "Date"

    except Exception as exc:
        log.warning("%s: yfinance fetch failed (%s) — skipping", safe, exc)
        return result

    # ── 4. Identify new rows ──────────────────────────────────────────────────
    if existing_df is not None and not existing_df.empty:
        last_known = existing_df.index.max()
        new_rows = raw[raw.index > last_known]
    else:
        new_rows = raw

    if new_rows.empty:
        log.info("%s: already up to date (latest: %s)", safe, raw.index.max().date())
        return result

    # ── 5. Keep only columns we care about ───────────────────────────────────
    keep_cols = [c for c in _REQUIRED_COLS if c in new_rows.columns]
    if "Close" not in keep_cols:
        log.warning("%s: 'Close' column missing in yfinance response", safe)
        return result

    new_rows = new_rows[keep_cols].copy()

    # ── 6. Append, save locally, and upload ──────────────────────────────────
    if existing_df is not None and not existing_df.empty:
        # Align columns between existing and new before concat
        for col in keep_cols:
            if col not in existing_df.columns:
                existing_df[col] = None
        existing_subset = existing_df[[c for c in keep_cols if c in existing_df.columns]]
        combined = pd.concat([existing_subset, new_rows]).sort_index()
        combined = combined[~combined.index.duplicated(keep="last")]
    else:
        combined = new_rows.sort_index()

    CSVS_TMP.mkdir(parents=True, exist_ok=True)
    combined.to_csv(local_path)
    upload_model_to_storage(str(local_path), storage_path)

    latest_date = new_rows.index.max()
    latest_close = float(new_rows["Close"].iloc[-1])

    log.info(
        "%s: appended %d row(s) up to %s  close=%.4f",
        safe,
        len(new_rows),
        latest_date.date(),
        latest_close,
    )

    result["scraped"] = True
    result["date"] = latest_date.date().isoformat()
    result["close"] = latest_close
    return result


def main() -> dict[str, dict]:
    """
    Scrape all companies from companies.json.

    Returns a dict mapping safe ticker → result dict.
    Called directly by run_daily_update.py.
    """
    CSVS_TMP.mkdir(parents=True, exist_ok=True)

    # Initialize Firebase (needed by download/upload helpers)
    get_db()

    companies = load_companies()

    ticker_filter = os.environ.get("NSE_TICKERS_FILTER", "").strip()
    if ticker_filter:
        allowed = {t.strip().upper() for t in ticker_filter.split(",") if t.strip()}
        companies = [c for c in companies if c["ticker"].upper() in allowed]
        log.info(
            "NSE_TICKERS_FILTER active — scraping %d company/companies: %s",
            len(companies),
            ", ".join(allowed),
        )

    results: dict[str, dict] = {}
    scraped_count = 0

    log.info("Scraping %d companies with up to 8 parallel workers...", len(companies))

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(scrape_company, c): c for c in companies}
        for fut in as_completed(futures):
            try:
                res = fut.result()
            except Exception as exc:
                company = futures[fut]
                safe = _safe_name(company["ticker"])
                log.error("Unexpected error scraping %s: %s", safe, exc, exc_info=True)
                res = {
                    "ticker": safe,
                    "scraped": False,
                    "date": TODAY,
                    "close": None,
                }
            results[res["ticker"]] = res
            if res["scraped"]:
                scraped_count += 1

    log.info(
        "Scraping complete: %d/%d companies updated.",
        scraped_count,
        len(companies),
    )
    return results


if __name__ == "__main__":
    main()
