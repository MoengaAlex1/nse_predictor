"""
rebuild_clean_history.py

Rebuilds clean OHLCV CSVs for all NSE companies from the authoritative
year-by-year archive.

Pipeline:
  1. Load every NSE_data_all_stocks_YYYY.csv (2000-2026) + the July-17 patch
  2. Maker-checker using the Previous column to detect decimal-point errors
  3. High/Low consistency check and clamping
  4. Rolling-median second pass to catch any remaining outliers
  5. Build OHLCV: Close, Open, High, Low, Volume, Is_Stale, Ticker
  6. Fill missing trading days (business days Mon-Fri) and mark stale rows
  7. Final validity filter: remove rows where Close <= 0
  8. Save to data/cleaned/ and upload to Firebase Storage

Usage:
  python pipeline/scripts/rebuild_clean_history.py [--dry-run] [--ticker ABSA_NR]
"""
import os
import sys
import logging
import argparse
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.push_to_firestore import (
    get_db,
    upload_model_to_storage,
)
from config import load_companies, DATA_CLEANED

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

ARCHIVE_DIR = Path(os.environ.get("NSE_ARCHIVE_DIR", str(Path.home() / "Downloads" / "archive")))
CSVS_TMP = Path(tempfile.gettempdir()) / "nse_rebuilt"
TODAY = pd.Timestamp(date.today())

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

# NSE circuit breaker: price cannot move more than 9.9% in one session
NSE_CIRCUIT_BREAKER = 0.099


def _safe_name(ticker: str) -> str:
    return ticker.replace(".", "_")


def _ticker_base(safe: str) -> str:
    return safe[:-3] if safe.endswith("_NR") else safe


def _rolling_median(s: pd.Series, window: int = 7) -> pd.Series:
    """Compute centred rolling median, forward/backward-filled to avoid NaN edges."""
    med = s.rolling(window, min_periods=2, center=True).median()
    med = med.where(med > 0).ffill().bfill()
    return med


def _load_archive_year(path: Path) -> Optional[pd.DataFrame]:
    """Load one year-file normalising column names and date formats."""
    try:
        df = pd.read_csv(path, low_memory=False, encoding="utf-8-sig", thousands=",")
        # Normalise column names: strip whitespace then title-case
        df.columns = [c.strip().title() for c in df.columns]

        # Need at least Date, Code and Day Price
        if "Date" not in df.columns or "Code" not in df.columns:
            return None
        if "Day Price" not in df.columns:
            return None

        # Numeric coercion for Day Price
        df["Day Price"] = pd.to_numeric(
            df["Day Price"].astype(str).str.replace(",", ""), errors="coerce"
        )
        if df["Day Price"].notna().sum() == 0:
            return None

        # Parse dates — multiple formats present across years
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, format="mixed")
        return df
    except Exception as exc:
        log.warning("Cannot parse %s: %s", path.name, exc)
        return None


def _maker_checker_fix(grp: pd.DataFrame) -> pd.DataFrame:
    """
    Use the Previous column (prior day's close) as an anchor to detect and
    correct decimal-point errors in Day Price.

    Rules applied in order (per-row, chronologically):
      1. Validate Previous[t] against Day Price[t-1]; correct Previous if 100x off.
      2. ratio = Day Price[t] / Previous[t]
         - ratio > 30  → 100x too large  → divide by 100
         - ratio < 0.033 → 100x too small → multiply by 100
         - ratio > 8   → possible 10x too large → confirm with rolling-7d-median
         - ratio < 0.125 → possible 10x too small → confirm with rolling-7d-median
      3. Skip if Previous is 0, NaN, or this is the first row for the company.

    Returns a copy of grp with Day Price corrected in-place.
    """
    grp = grp.copy().reset_index(drop=True)

    prices = grp["Day Price"].astype(float).copy()
    previous = grp["Previous"].astype(float).copy() if "Previous" in grp.columns else pd.Series(np.nan, index=grp.index)

    # Pre-compute rolling median on uncorrected prices for secondary check
    med = _rolling_median(prices)

    for i in range(len(grp)):
        p = prices.iloc[i]
        prev = previous.iloc[i] if i > 0 else np.nan

        # Validate Previous[t] against the (already-corrected) Day Price[t-1]
        if i > 0 and not np.isnan(prev) and prev > 0:
            prior_close = prices.iloc[i - 1]
            if prior_close > 0:
                prev_ratio = prev / prior_close
                if prev_ratio > 30 or prev_ratio < 0.033:
                    # Previous itself is 100x off; correct it before using as anchor
                    if prev_ratio > 30:
                        prev = prev / 100.0
                    else:
                        prev = prev * 100.0
                    previous.iloc[i] = prev

        # Skip if no usable anchor
        if i == 0 or np.isnan(prev) or prev <= 0:
            # Recompute median contribution for later rows
            continue

        if np.isnan(p) or p <= 0:
            continue

        ratio = p / prev
        m = med.iloc[i] if not np.isnan(med.iloc[i]) and med.iloc[i] > 0 else None

        if ratio > 30:
            # Definite 100x error
            prices.iloc[i] = round(p / 100.0, 4)
        elif ratio < 0.033:
            # Definite 100x shortfall
            prices.iloc[i] = round(p * 100.0, 4)
        elif ratio > 8 and m is not None:
            # Possible 10x error: confirm with rolling median
            if (p / m) > 5.0:
                prices.iloc[i] = round(p / 100.0, 4)
        elif ratio < 0.125 and m is not None:
            # Possible 10x shortfall: confirm with rolling median
            if (p / m) < 0.2:
                prices.iloc[i] = round(p * 100.0, 4)

    grp["Day Price"] = prices
    return grp


def _fix_high_low(grp: pd.DataFrame) -> pd.DataFrame:
    """
    Step 2: High/Low consistency check after Close has been corrected.

    For each row:
      - Day High should be in [Close * 0.5, Close * 2.0].
        If outside: try dividing by 100; if that brings it into range, fix.
        Otherwise clamp to Close * (1 + NSE_CIRCUIT_BREAKER).
      - Day Low same logic; clamp floor to Close * (1 - NSE_CIRCUIT_BREAKER).
    """
    grp = grp.copy()
    close = grp["Day Price"].astype(float)

    for col, is_high in (("Day High", True), ("Day Low", False)):
        if col not in grp.columns:
            continue

        vals = grp[col].astype(float).copy()

        for i in range(len(grp)):
            c = close.iloc[i]
            v = vals.iloc[i]
            if np.isnan(c) or c <= 0 or np.isnan(v) or v <= 0:
                continue

            lo_bound = c * 0.5
            hi_bound = c * 2.0

            if is_high:
                if v < lo_bound or v > hi_bound:
                    candidate = v / 100.0
                    if lo_bound <= candidate <= hi_bound:
                        vals.iloc[i] = round(candidate, 4)
                    else:
                        # Clamp to NSE circuit breaker ceiling
                        vals.iloc[i] = round(c * (1.0 + NSE_CIRCUIT_BREAKER), 4)
                # Ensure High >= Close
                if vals.iloc[i] < c:
                    vals.iloc[i] = c
            else:
                if v < lo_bound or v > hi_bound:
                    candidate = v / 100.0
                    if lo_bound <= candidate <= hi_bound:
                        vals.iloc[i] = round(candidate, 4)
                    else:
                        # Clamp to NSE circuit breaker floor
                        vals.iloc[i] = round(c * (1.0 - NSE_CIRCUIT_BREAKER), 4)
                # Ensure Low <= Close
                if vals.iloc[i] > c:
                    vals.iloc[i] = c

        grp[col] = vals

    return grp


def _rolling_median_second_pass(s: pd.Series) -> pd.Series:
    """
    Step 3: Rolling-median second pass.
    Correct any price where price / rolling_7d_median > 15 or < 0.067.
    """
    s = s.copy().astype(float)
    med = _rolling_median(s)

    ratio = s / med
    too_high = ratio > 15.0
    too_low = ratio < 0.067

    s[too_high] = (s[too_high] / 100.0).round(4)
    s[too_low] = (s[too_low] * 100.0).round(4)

    return s


def _build_ohlcv_for_ticker(grp: pd.DataFrame) -> pd.DataFrame:
    """
    Step 4: Build the OHLCV DataFrame from cleaned columns.

    Open  = previous row's Day Price (shift by 1, fill with Close for first row)
    High  = cleaned Day High
    Low   = cleaned Day Low
    Close = cleaned Day Price
    Volume = numeric Volume (0 if missing)
    Is_Stale = 0
    Ticker = set by caller
    """
    grp = grp.sort_values("Date").set_index("Date")
    grp = grp[~grp.index.duplicated(keep="last")]

    close = grp["Day Price"].astype(float)
    high = grp["Day High"].astype(float) if "Day High" in grp.columns else close.copy()
    low = grp["Day Low"].astype(float) if "Day Low" in grp.columns else close.copy()
    volume = (
        pd.to_numeric(grp["Volume"].astype(str).str.replace(",", ""), errors="coerce")
        if "Volume" in grp.columns
        else pd.Series(0, index=grp.index)
    )

    open_ = close.shift(1).fillna(close)

    ohlcv = pd.DataFrame(
        {
            "Open": open_.round(4),
            "High": high.round(4),
            "Low": low.round(4),
            "Close": close.round(4),
            "Volume": volume.fillna(0).astype(int),
            "Is_Stale": 0,
        },
        index=grp.index,
    )
    ohlcv.index.name = "Date"
    return ohlcv


def _fill_missing_trading_days(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """
    Step 5: Reindex to full Mon-Fri business-day range.

    - Forward-fill OHLCV for missing days.
    - Set Is_Stale=1 for all forward-filled (inserted) rows.
    - Set Is_Stale=1 for any 3+ consecutive rows with identical Close.
    """
    if ohlcv.empty:
        return ohlcv

    full_range = pd.bdate_range(start=ohlcv.index.min(), end=ohlcv.index.max())
    original_dates = set(ohlcv.index)

    ohlcv = ohlcv.reindex(full_range)
    ohlcv.index.name = "Date"

    # Mark inserted rows as stale before forward-filling
    inserted = [d for d in ohlcv.index if d not in original_dates]
    ohlcv["Is_Stale"] = 0
    ohlcv.loc[inserted, "Is_Stale"] = 1

    # Forward-fill OHLCV columns
    for col in ("Open", "High", "Low", "Close", "Volume"):
        ohlcv[col] = ohlcv[col].ffill()

    ohlcv["Volume"] = ohlcv["Volume"].fillna(0).astype(int)

    # Mark stale: any 3+ consecutive rows with identical Close
    close = ohlcv["Close"]
    same_as_prev1 = close == close.shift(1)
    same_as_prev2 = close == close.shift(2)
    consecutive_stale = same_as_prev1 & same_as_prev2
    # Also tag the first two rows of a run (where they match the next two)
    same_as_next1 = close == close.shift(-1)
    same_as_next2 = close == close.shift(-2)
    start_of_run = same_as_next1 & same_as_next2
    ohlcv.loc[consecutive_stale | start_of_run, "Is_Stale"] = 1

    return ohlcv


def build_archive_map() -> dict[str, pd.DataFrame]:
    """
    Load all archive files, apply full cleaning pipeline, return {ticker_base: df}.

    Cleaning applied per company:
      1. Maker-checker fix using Previous column
      2. High/Low consistency fix
      3. Rolling-median second pass
      4. Build OHLCV
      5. Fill missing trading days
    """
    frames: list[pd.DataFrame] = []

    year_files = sorted(ARCHIVE_DIR.glob("NSE_data_all_stocks_*.csv"))
    log.info("Found %d archive year-files in %s", len(year_files), ARCHIVE_DIR)

    for path in year_files:
        df = _load_archive_year(path)
        if df is None or df.empty:
            continue
        frames.append(df)
        log.debug("Loaded %s (%d rows)", path.name, len(df))

    # Also load the patch file
    patch = ARCHIVE_DIR / "NSE_patch_2026-07-17.csv"
    if patch.exists():
        df_patch = _load_archive_year(patch)
        if df_patch is not None and not df_patch.empty:
            frames.append(df_patch)
            log.info("Loaded patch file: %s (%d rows)", patch.name, len(df_patch))
    else:
        log.warning("Patch file not found: %s", patch)

    if not frames:
        raise RuntimeError(f"No archive files found in {ARCHIVE_DIR}!")

    raw = pd.concat(frames, ignore_index=True)
    log.info("Total raw rows across all years: %d", len(raw))

    # Normalise Code
    raw["Code"] = raw["Code"].astype(str).str.strip().str.upper()
    # Drop junk rows (header repeats, non-ticker codes)
    raw = raw[raw["Code"].str.match(r"^[A-Z]{2,8}(-[A-Z0-9]+)?$", na=False)]
    raw = raw.dropna(subset=["Date", "Day Price"])
    # Remove future dates
    raw = raw[raw["Date"] <= TODAY]

    # Numeric coercion for remaining columns
    for col in ("Day Low", "Day High", "Volume", "Previous"):
        if col in raw.columns:
            raw[col] = pd.to_numeric(
                raw[col].astype(str).str.replace(",", ""), errors="coerce"
            )

    raw = raw.sort_values(["Code", "Date"]).reset_index(drop=True)
    log.info("Cleaned raw rows after filtering: %d across %d codes", len(raw), raw["Code"].nunique())

    result: dict[str, pd.DataFrame] = {}

    log.info("Running per-company cleaning pipeline …")
    for code, grp in raw.groupby("Code"):
        grp = grp.copy()

        # Step 1: Maker-checker using Previous
        grp = _maker_checker_fix(grp)

        # Step 2: High/Low consistency
        grp = _fix_high_low(grp)

        # Step 3: Rolling-median second pass on Close
        grp["Day Price"] = _rolling_median_second_pass(
            grp["Day Price"].reset_index(drop=True)
        ).values

        # Step 4: Build OHLCV
        try:
            ohlcv = _build_ohlcv_for_ticker(grp)
        except Exception as exc:
            log.warning("OHLCV build failed for %s: %s", code, exc)
            continue

        # Step 5: Fill missing trading days
        ohlcv = _fill_missing_trading_days(ohlcv)

        # Step 6: Remove rows where Close <= 0
        ohlcv = ohlcv[ohlcv["Close"] > 0]

        if ohlcv.empty:
            continue

        # Map archive code to our ticker base
        base = ARCHIVE_CODE_MAP.get(code, code)
        if base in result:
            result[base] = pd.concat([result[base], ohlcv]).sort_index()
            result[base] = result[base][~result[base].index.duplicated(keep="last")]
        else:
            result[base] = ohlcv

    log.info("Archive map built: %d unique company bases", len(result))
    return result


def clean_and_upload(
    safe: str,
    archive_df: Optional[pd.DataFrame],
    dry_run: bool = False,
) -> dict:
    """
    Validate, tag, save and upload a single ticker's cleaned OHLCV data.

    Steps:
      - The archive_df is already fully cleaned (Steps 1-5 done in build_archive_map).
      - Add Ticker column.
      - Save to CSVS_TMP and DATA_CLEANED.
      - Upload to Firebase Storage.
    """
    if archive_df is None or archive_df.empty:
        return {"safe": safe, "rows": 0, "status": "no_data"}

    combined = archive_df.sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]

    # Ensure Ticker column
    combined = combined.copy()
    combined["Ticker"] = _ticker_base(safe)

    # Ensure Is_Stale is present (should be, but guard against edge cases)
    if "Is_Stale" not in combined.columns:
        combined["Is_Stale"] = 0

    # Final validity: Close must be positive
    combined = combined[combined["Close"] > 0]

    rows = len(combined)
    date_from = combined.index.min().date() if rows else None
    date_to = combined.index.max().date() if rows else None

    if not dry_run and rows > 0:
        CSVS_TMP.mkdir(parents=True, exist_ok=True)
        out_path = CSVS_TMP / f"{safe}_cleaned.csv"
        combined.to_csv(out_path)

        # Copy to repo data/cleaned/ so seed_from_csvs.py can read it
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


def main(dry_run: bool = False, ticker_filter: Optional[str] = None) -> None:
    CSVS_TMP.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        get_db()

    # Build the fully-cleaned archive map (Steps 1-5 happen here per company)
    log.info("Loading and cleaning archive data from %s …", ARCHIVE_DIR)
    archive_map = build_archive_map()
    log.info("Archive covers %d unique company codes", len(archive_map))

    # Our company list
    companies = load_companies()
    if ticker_filter:
        companies = [c for c in companies if _safe_name(c["ticker"]) == ticker_filter]

    totals: dict[str, int] = {"processed": 0, "rows_total": 0, "uploaded": 0, "no_data": 0, "dry_run": 0}
    summaries: list[dict] = []

    for company in companies:
        safe = _safe_name(company["ticker"])
        base = _ticker_base(safe)

        archive_df = archive_map.get(base)

        result = clean_and_upload(safe, archive_df, dry_run=dry_run)
        totals["processed"] += 1
        totals["rows_total"] += result["rows"]

        if result["status"] == "uploaded":
            totals["uploaded"] += 1
        elif result["status"] == "dry_run":
            totals["dry_run"] += 1
        elif result["status"] == "no_data":
            totals["no_data"] += 1

        summaries.append(result)

    # Per-company summary table
    print()
    print(f"{'Ticker':<14} {'Rows':>6}  {'From':<12}  {'To':<12}  Status")
    print("-" * 60)
    for r in summaries:
        date_from = str(r.get("date_from", "?"))
        date_to = str(r.get("date_to", "?"))
        print(
            f"{r['safe']:<14} {r['rows']:>6}  {date_from:<12}  {date_to:<12}  {r['status']}"
        )

    print()
    print("=" * 60)
    print(f"Processed  : {totals['processed']} companies")
    print(f"Total rows : {totals['rows_total']:,}")
    print(f"Uploaded   : {totals['uploaded']}")
    print(f"No data    : {totals['no_data']}")
    if dry_run:
        print(f"(DRY RUN — {totals['dry_run']} companies would have been uploaded)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild clean NSE history from archive")
    parser.add_argument("--dry-run", action="store_true", help="Report only, no upload")
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Process only one safe ticker (e.g. ABSA_NR)",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run, ticker_filter=args.ticker)
