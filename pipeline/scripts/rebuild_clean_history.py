"""
rebuild_clean_history.py

Rebuilds clean OHLCV CSVs for all NSE companies from the authoritative
year-by-year archive at C:/Users/moeng/Downloads/archive/.

Pipeline:
  1. Load every NSE_data_all_stocks_YYYY.csv (2007-2026) + the July-17 patch
  2. Fix the 100x decimal-point error: rows where Day Price > 30x rolling
     median are divided by 100 to restore the correct price
  3. Map archive Code (e.g. ABSA) to our safe ticker (ABSA_NR)
  4. Reconstruct OHLCV: Close=corrected Day Price, High=Day High,
     Low=corrected Day Low, Open=previous day's Close, Volume=Volume
  5. Append the July-20 prices already in Firebase Storage
  6. Upload cleaned CSVs to Firebase Storage at data/cleaned/{safe}_cleaned.csv

Usage:
  python pipeline/scripts/rebuild_clean_history.py [--dry-run] [--ticker ABSA_NR]
"""
import sys
import logging
import argparse
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.push_to_firestore import (
    get_db,
    download_model_from_storage,
    upload_model_to_storage,
)
from config import load_companies, DATA_CLEANED

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

ARCHIVE_DIR = Path(r"C:/Users/moeng/Downloads/archive")
CSVS_TMP    = Path(r"C:/Users/moeng/AppData/Local/Temp/nse_rebuilt")
TODAY       = pd.Timestamp(date.today())

# Multiplier threshold: if Day Price > median * this factor, it's a 100x error
SPIKE_RATIO = 30.0

# Archive Code → our ticker base (handles special cases; rest auto-map CODE→CODE)
ARCHIVE_CODE_MAP: dict[str, str] = {
    "FAHR": "HAFR",   # archive typo for Home Afrika
    "ORCH": "OCH",
    "MSC":  "SMER",
    "ARM":  "CARB",   # ARM Cement was Carbacid predecessor listing
    "NBK":  "NBV",
    "TCL":  "TOTL",
    "CABL": "CABL",
    "DCON": "DCON",
    "HBE":  "HBE",
    "LAPR": "LAPR",
    "SKL":  "SKL",
}


def _safe_name(ticker: str) -> str:
    return ticker.replace(".", "_")


def _ticker_base(safe: str) -> str:
    return safe[:-3] if safe.endswith("_NR") else safe


def _fix_decimal_errors(series: pd.Series, rolling_window: int = 7) -> pd.Series:
    """
    Detect rows where a price was stored 100x too large (missing decimal) and
    divide them by 100.  Operates on a per-company time series.
    """
    s = pd.Series(series, dtype=float).reset_index(drop=True)
    if len(s) < 3:
        return s

    # Iterative: correct the most extreme outlier, recompute median, repeat
    for _ in range(10):
        med = s.rolling(rolling_window, min_periods=2, center=True).median()
        # Protect against zero/NaN medians
        med = med.where(med > 0).ffill().bfill()
        ratio = s / med
        bad = ratio > SPIKE_RATIO
        if not bad.any():
            break
        s[bad] = (s[bad] / 100.0).round(4)

    return s


def _load_archive_year(path: Path) -> pd.DataFrame | None:
    """Load one year-file normalising column names and date formats."""
    try:
        df = pd.read_csv(path, low_memory=False, encoding="utf-8-sig", thousands=",")
        # Normalise column names to title-case
        df.columns = [c.strip().title() for c in df.columns]
        # Need both Date and Code columns (skip annual-summary files with no daily data)
        if "Date" not in df.columns or "Code" not in df.columns:
            return None
        # Must have Day Price to be useful
        if "Day Price" not in df.columns:
            return None
        # Skip files where Day Price column is entirely NaN or non-numeric
        df["Day Price"] = pd.to_numeric(
            df["Day Price"].astype(str).str.replace(",", ""), errors="coerce"
        )
        if df["Day Price"].notna().sum() == 0:
            return None
        # Parse dates — multiple formats are present across years
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed")
        return df
    except Exception as exc:
        log.warning("Cannot parse %s: %s", path.name, exc)
        return None


def build_archive_map() -> dict[str, pd.DataFrame]:
    """
    Load all archive files, fix decimal errors, return {ticker_base: df}.
    df columns: Date(index), Open, High, Low, Close, Volume
    """
    frames: list[pd.DataFrame] = []

    for path in sorted(ARCHIVE_DIR.glob("NSE_data_all_stocks_*.csv")):
        df = _load_archive_year(path)
        if df is None or df.empty:
            continue
        frames.append(df)

    # Also load the July-17 patch
    patch = ARCHIVE_DIR / "NSE_patch_2026-07-17.csv"
    if patch.exists():
        df_patch = _load_archive_year(patch)
        if df_patch is not None and not df_patch.empty:
            frames.append(df_patch)

    if not frames:
        raise RuntimeError("No archive files found!")

    raw = pd.concat(frames, ignore_index=True)

    # Normalize Code
    raw["Code"] = raw["Code"].astype(str).str.strip().str.upper()
    # Drop junk rows (index rows, header repeats, codes containing non-alpha)
    raw = raw[raw["Code"].str.match(r"^[A-Z]{2,8}(-[A-Z0-9]+)?$", na=False)]
    raw = raw.dropna(subset=["Date", "Day Price"])

    # Remove dates in the future
    raw = raw[raw["Date"] <= TODAY]

    # Numeric columns (Day Price already converted in _load_archive_year)
    for col in ["Day Low", "Day High", "Volume", "Previous"]:
        if col in raw.columns:
            raw[col] = pd.to_numeric(raw[col].astype(str).str.replace(",", ""), errors="coerce")

    raw = raw.sort_values(["Code", "Date"]).reset_index(drop=True)

    # Fix 100x decimal errors per company
    log.info("Fixing decimal-point errors per company …")
    corrected = []
    for code, grp in raw.groupby("Code"):
        grp = grp.copy()
        grp["Day Price"] = _fix_decimal_errors(grp["Day Price"]).values
        # Day Low can also get corrupted
        if "Day Low" in grp.columns:
            grp["Day Low"] = _fix_decimal_errors(grp["Day Low"]).values
        # Day High is usually clean; fix just in case
        if "Day High" in grp.columns:
            grp["Day High"] = _fix_decimal_errors(grp["Day High"]).values
        corrected.append(grp)
    raw = pd.concat(corrected, ignore_index=True)

    # Build OHLCV per company
    log.info("Building OHLCV time series …")
    result: dict[str, pd.DataFrame] = {}

    for code, grp in raw.groupby("Code"):
        grp = grp.sort_values("Date").set_index("Date")
        grp = grp[~grp.index.duplicated(keep="last")]

        close  = grp["Day Price"]
        high   = grp.get("Day High", close)
        low    = grp.get("Day Low",  close)
        volume = grp.get("Volume",   pd.Series(0, index=grp.index))

        # Open = previous day's close (shift by 1)
        open_  = close.shift(1).fillna(close)

        ohlcv = pd.DataFrame({
            "Open":   open_.round(4),
            "High":   high.round(4),
            "Low":    low.round(4),
            "Close":  close.round(4),
            "Volume": volume.fillna(0).astype(int),
        }, index=grp.index)
        ohlcv.index.name = "Date"

        # Final sanity: High >= Close >= Low > 0
        valid = (
            (ohlcv["Close"] > 0) &
            (ohlcv["High"]  >= ohlcv["Close"] * 0.5) &
            (ohlcv["Low"]   <= ohlcv["Close"] * 2.0)
        )
        ohlcv = ohlcv[valid]

        # Map archive code to our ticker base
        base = ARCHIVE_CODE_MAP.get(code, code)
        if base in result:
            result[base] = pd.concat([result[base], ohlcv]).sort_index()
            result[base] = result[base][~result[base].index.duplicated(keep="last")]
        else:
            result[base] = ohlcv

    return result


def get_storage_prices(safe: str) -> pd.DataFrame | None:
    """Download the current Storage CSV to get any real prices we already scraped."""
    storage_path = f"data/cleaned/{safe}_cleaned.csv"
    local_path = CSVS_TMP / f"{safe}_storage.csv"
    try:
        ok = download_model_from_storage(storage_path, str(local_path))
        if not ok:
            return None
        df = pd.read_csv(local_path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if not date_col:
            return None
        df[date_col] = pd.to_datetime(df[date_col], format="mixed")
        df = df.set_index(date_col).sort_index()
        df.index.name = "Date"
        # Keep only Volume>0 rows (real scraped prices, not forward-fills)
        if "Volume" in df.columns:
            df = df[df["Volume"] > 0]
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
    except Exception as exc:
        log.debug("Storage download failed for %s: %s", safe, exc)
        return None


def clean_and_upload(
    safe: str,
    archive_df: pd.DataFrame | None,
    storage_df: pd.DataFrame | None,
    dry_run: bool = False,
) -> dict:
    """
    Merge archive + Storage data, validate, upload.
    Returns summary dict.
    """
    frames = []
    if archive_df is not None and not archive_df.empty:
        frames.append(archive_df)
    if storage_df is not None and not storage_df.empty:
        # Only keep Storage rows that are newer than what archive covers
        if frames:
            arch_max = frames[0].index.max()
            storage_newer = storage_df[storage_df.index > arch_max]
        else:
            storage_newer = storage_df
        if not storage_newer.empty:
            frames.append(storage_newer[["Open", "High", "Low", "Close", "Volume"]])

    if not frames:
        return {"safe": safe, "rows": 0, "status": "no_data"}

    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]

    # Final validation: remove any remaining spikes by iterative rolling-median
    combined["Close"] = _fix_decimal_errors(combined["Close"]).values
    combined["High"]  = _fix_decimal_errors(combined["High"]).values
    combined["Low"]   = _fix_decimal_errors(combined["Low"]).values
    combined["Open"]  = _fix_decimal_errors(combined["Open"]).values

    # Drop rows with Close <= 0 or Volume < 0
    combined = combined[(combined["Close"] > 0)]

    # Add metadata columns expected by the pipeline
    combined["Ticker"]   = _ticker_base(safe)
    combined["Is_Stale"] = 0

    rows = len(combined)
    date_from = combined.index.min().date() if rows else None
    date_to   = combined.index.max().date() if rows else None

    if not dry_run and rows > 0:
        CSVS_TMP.mkdir(parents=True, exist_ok=True)
        out_path = CSVS_TMP / f"{safe}_cleaned.csv"
        combined.to_csv(out_path)
        # Also copy to repo data/cleaned/ so seed_from_csvs.py can read it
        DATA_CLEANED.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out_path, DATA_CLEANED / f"{safe}_cleaned.csv")
        storage_path = f"data/cleaned/{safe}_cleaned.csv"
        upload_model_to_storage(str(out_path), storage_path)
        status = "uploaded"
    else:
        status = "dry_run" if dry_run else "empty"

    return {
        "safe": safe,
        "rows": rows,
        "date_from": date_from,
        "date_to": date_to,
        "status": status,
    }


def main(dry_run: bool = False, ticker_filter: str | None = None):
    CSVS_TMP.mkdir(parents=True, exist_ok=True)
    if not dry_run:
        get_db()

    # Build archive map
    log.info("Loading and correcting archive data …")
    archive_map = build_archive_map()
    log.info("Archive covers %d unique company codes", len(archive_map))

    # Our company list
    companies = load_companies()
    if ticker_filter:
        companies = [c for c in companies if _safe_name(c["ticker"]) == ticker_filter]

    totals = {"processed": 0, "rows_total": 0, "uploaded": 0, "no_data": 0}

    for company in companies:
        safe = _safe_name(company["ticker"])
        base = _ticker_base(safe)

        archive_df  = archive_map.get(base)
        storage_df  = get_storage_prices(safe)

        result = clean_and_upload(safe, archive_df, storage_df, dry_run=dry_run)
        totals["processed"] += 1
        totals["rows_total"] += result["rows"]
        if result["status"] == "uploaded":
            totals["uploaded"] += 1
        elif result["status"] == "no_data":
            totals["no_data"] += 1

        icon = "uploaded" if result["status"] == "uploaded" else result["status"]
        print(
            f"{safe:<12}: {result['rows']:>5} rows"
            f" | {result.get('date_from','?')} .. {result.get('date_to','?')}"
            f" | {icon}"
        )

    print()
    print("=" * 60)
    print(f"Processed : {totals['processed']} companies")
    print(f"Total rows: {totals['rows_total']:,}")
    print(f"Uploaded  : {totals['uploaded']}")
    print(f"No data   : {totals['no_data']}")
    if dry_run:
        print("(DRY RUN — nothing uploaded)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild clean NSE history from archive")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no upload")
    parser.add_argument("--ticker", type=str, default=None, help="Process only one safe ticker (e.g. ABSA_NR)")
    args = parser.parse_args()
    main(dry_run=args.dry_run, ticker_filter=args.ticker)
