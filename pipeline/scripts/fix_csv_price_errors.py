"""
fix_csv_price_errors.py

Corrects known decimal-point errors in data/cleaned/*.csv files.

Two classes of error are handled:

  1. Year-level shift — an entire year's prices are 10x too high because
     the data source omitted the decimal. Detected when the year median
     diverges >4x from the cross-year dataset median.

  2. Row-level spike — individual dates have a price that is far above the
     rolling 7-day median of surrounding dates, indicating a single missing
     decimal. Detected via rolling-median ratio > SPIKE_RATIO.

Correction strategy: divide by 10 (or 100 for 100x errors), but ONLY when
the corrected value falls within a sensible range of the local rolling median.
If the corrected value is also out of range, the row is removed instead.

Usage:
    python pipeline/scripts/fix_csv_price_errors.py [--dry-run] [--ticker EQTY_NR]
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies, DATA_CLEANED

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# A single-day price ratio this high vs the rolling 7-day median is a clear
# 10x decimal error. NSE's 9.9 % daily circuit breaker makes a genuine 5.5x
# single-day move impossible.
SPIKE_RATIO = 5.5

OHLC_COLS = ["Open", "High", "Low", "Close"]


# ── Rolling-median helpers ─────────────────────────────────────────────────────

def _rolling_median(s: pd.Series, window: int = 7) -> pd.Series:
    med = s.rolling(window, min_periods=2, center=True).median()
    return med.where(med > 0).ffill().bfill()


def _fix_row_spikes(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Detect and correct row-level decimal spikes using a two-window rolling median.

    Two passes are run:
      Pass 1 — narrow window (7 days): catches isolated spikes.
      Pass 2 — wide window (30 days): catches clustered wrong-value blocks
        (e.g. KCB 2007 where wrong values are ~20 % of the year; a 30-day
        window still has enough correct values to give a reliable median).

    For each flagged row:
      - ratio > 30  → try /100
      - ratio > SPIKE_RATIO → try /10
    Accept the correction when the adjusted value is within 3× the rolling
    median. Otherwise remove the row entirely.
    """
    if df.empty:
        return df, 0

    total_corrected = 0

    for window in (7, 30):
        close = df["Close"].astype(float).copy()
        med = _rolling_median(close, window=window)
        ratio = close / med.replace(0, np.nan)

        removed_idx: list = []
        changed_this_pass = 0

        for idx in df.index:
            r = ratio.loc[idx]
            c = float(df.at[idx, "Close"])
            m = med.loc[idx]

            if not np.isfinite(r) or m <= 0:
                continue

            if r > 30:
                factor = 100.0
            elif r > SPIKE_RATIO:
                factor = 10.0
            else:
                continue

            adjusted = c / factor
            if m / 3.0 <= adjusted <= m * 3.0:
                for col in OHLC_COLS:
                    if col in df.columns:
                        df.at[idx, col] = round(float(df.at[idx, col]) / factor, 4)
                changed_this_pass += 1
            else:
                removed_idx.append(idx)

        if removed_idx:
            df = df.drop(index=removed_idx)
            changed_this_pass += len(removed_idx)

        total_corrected += changed_this_pass

    return df, total_corrected


def _fix_within_year_outliers(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Catch rows that are ~10x above the year median even when they appear in
    contiguous runs (which fool the rolling-median window).

    For each calendar year:
      1. Compute the year median.
      2. Flag rows where Close > 8 × year_median.
      3. If Close/10 lands within 2 × year_median, correct by /10.
         Otherwise remove.

    This is the key fix for cases like KCB 2007, where 20% of values are
    10x too high and appear in long blocks that bias the rolling median.
    The year median itself stays correct because the correct values are the
    majority (~80%).
    """
    if df.empty:
        return df, 0

    close = df["Close"].astype(float)
    corrected = 0
    removed_idx: list = []

    for yr, grp_idx in close.groupby(df.index.year).groups.items():
        yr_close = close.loc[grp_idx]
        yr_med = float(yr_close.median())
        if yr_med <= 0:
            continue

        threshold = yr_med * 8.0

        for idx in grp_idx:
            c = float(df.at[idx, "Close"])
            if c <= threshold:
                continue

            # Try /10 correction
            adjusted = c / 10.0
            if adjusted <= yr_med * 2.0:
                for col in OHLC_COLS:
                    if col in df.columns:
                        df.at[idx, col] = round(float(df.at[idx, col]) / 10.0, 4)
                corrected += 1
            else:
                removed_idx.append(idx)

    if removed_idx:
        df = df.drop(index=removed_idx)
        corrected += len(removed_idx)

    return df, corrected


def _flag_poisoned_years(year_medians: dict[int, float]) -> set[int]:
    """
    Identify years whose prices are ~10x too high via adjacent-year jump detection.

    Strategy: scan year-medians chronologically. If year[y] / first-non-poisoned-
    successor > JUMP_THRESHOLD (6.5x), year[y] is flagged as poisoned.

    "First non-poisoned successor" skips years that are themselves flagged so that
    a block of several consecutive poisoned years (e.g. EQTY 2007 AND 2008) can
    all be traced back to the first clean reference year.

    Threshold of 6.5x catches follow-on poisoned years that become detectable only
    AFTER the primary poisoned year is corrected in an earlier iteration. Example:
      EQTY 2007 (130 KES) and 2008 (189 KES) are both 10x wrong. After iteration 1
      fixes 2008 → 18.9, the 2007/2008 ratio becomes 130/18.9 = 6.88x — just above
      6.5, so iteration 2 catches 2007.

    Legitimate multi-year price swings on NSE stay well under 5x in a single
    year-to-year step (circuit-breaker limited to 9.9 % per day). IMH, CTUM, GLD
    checked empirically — max adjacent ratio ≤ 2.1x.
    """
    JUMP_THRESHOLD = 6.5

    flagged: set[int] = set()
    if not year_medians:
        return flagged

    years_sorted = sorted(year_medians)

    for i, yr in enumerate(years_sorted):
        ym = year_medians[yr]
        # Find the nearest SUBSEQUENT year not already flagged
        clean_successor_med = None
        for j in range(i + 1, len(years_sorted)):
            yr2 = years_sorted[j]
            if yr2 not in flagged and year_medians[yr2] > 0:
                clean_successor_med = year_medians[yr2]
                break
        if clean_successor_med is None or clean_successor_med <= 0:
            continue
        if ym / clean_successor_med >= JUMP_THRESHOLD:
            flagged.add(yr)

    return flagged


def _fix_year_shifts(df: pd.DataFrame, ticker: str) -> tuple[pd.DataFrame, int]:
    """
    Detect years where the ENTIRE year's prices are 10x too high.

    Strategy:
      1. Iteratively identify "poisoned" years via _flag_poisoned_years.
      2. For each flagged year, confirm that ≥80 % of its rows have Close
         above 3× the p20 reference (guards against flagging years with genuine
         price peaks driven by a few outlier days).
      3. Divide all OHLC values in confirmed years by 10, then refresh year
         medians and repeat until no more poisoned years are found.

    Iterating is necessary because a block of consecutive poisoned years (e.g.
    EQTY 2007 and 2008) may only become mutually detectable once the first
    correction changes the year-median landscape. Example:
      Pass 1: fixes 2008 (189 KES → 18.9). Now 2007 (130) / 2008 (18.9) = 6.88x.
      Pass 2: fixes 2007 (130 KES → 13.0).

    For years that are only PARTIALLY wrong (some correct rows mixed with
    outlier rows), the row-spike pass (_fix_row_spikes) handles the individual
    outliers and this pass leaves those years alone.
    """
    if df.empty:
        return df, 0

    close = df["Close"].astype(float)

    def _year_medians() -> dict[int, float]:
        return {int(yr): float(grp.median()) for yr, grp in close.groupby(df.index.year)}

    year_medians = _year_medians()
    if not year_medians:
        return df, 0

    total_corrected = 0

    for _ in range(20):  # cap at 20 iterations to prevent infinite loops
        sorted_meds = sorted(year_medians.values())
        p20_idx = max(0, int(len(sorted_meds) * 0.20) - 1)
        ref = sorted_meds[p20_idx]
        if ref <= 0:
            break

        suspect_years = _flag_poisoned_years(year_medians)
        if not suspect_years:
            break

        made_correction = False
        for yr in sorted(suspect_years):
            ym = year_medians[yr]

            # Confirm: ≥80% of this year's values are above 3× the p20 reference
            yr_mask = df.index.year == yr
            yr_close = close[yr_mask]
            frac_high = (yr_close > ref * 3.0).mean()

            if frac_high < 0.80:
                log.debug(
                    "%s %d: year_median=%.2f flagged but only %.0f%% are high "
                    "— leaving for row-spike pass",
                    ticker, yr, ym, frac_high * 100,
                )
                continue

            log.info(
                "%s %d: year_median=%.2f is %.1fx p20-ref=%.2f → dividing entire year by 10",
                ticker, yr, ym, ym / ref if ref > 0 else 0, ref,
            )
            for col in OHLC_COLS:
                if col in df.columns:
                    df.loc[yr_mask, col] = (df.loc[yr_mask, col].astype(float) / 10.0).round(4)

            close = df["Close"].astype(float)
            year_medians[yr] = float(close[yr_mask].median())
            total_corrected += int(yr_mask.sum())
            made_correction = True

        if not made_correction:
            break

    return df, total_corrected


def _fix_single_value_100x(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Catch 100x errors in very small datasets where the rolling-median pass
    has no reference context (e.g. TRFC_NR which has only 1 CSV row).

    NSE stocks rarely exceed KES 500. If the sole / majority Close value is
    >100 AND dividing by 100 lands in [0.1, 100], apply the correction.
    Only fires when the dataset has ≤10 rows.
    """
    if len(df) > 10:
        return df, 0

    close = df["Close"].astype(float)
    overall_med = float(close.median())
    if overall_med <= 0:
        return df, 0

    corrected = 0
    for idx in df.index:
        c = float(df.at[idx, "Close"])
        candidate = c / 100.0
        # 100x error if: value is unusually high AND /100 lands in [0.1, 100]
        if c > 100 and 0.1 <= candidate <= 100:
            for col in OHLC_COLS:
                if col in df.columns:
                    df.at[idx, col] = round(float(df.at[idx, col]) / 100.0, 4)
            corrected += 1
            log.info("  Row %s: Close %.2f → %.4f (÷100)", idx.date(), c, candidate)

    return df, corrected


# ── Per-ticker pipeline ────────────────────────────────────────────────────────

def _load_csv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None or "Close" not in df.columns:
            return None
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=False, format="mixed")
        df = df.set_index(date_col).sort_index()
        df.index.name = "Date"
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = df.dropna(subset=["Close"])
        for col in OHLC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
    except Exception as exc:
        log.warning("Cannot load %s: %s", path, exc)
        return None


def fix_ticker(csv_path: Path, dry_run: bool = False) -> dict:
    ticker = csv_path.stem.replace("_cleaned", "")
    df_full = _load_csv(csv_path)
    if df_full is None or df_full.empty:
        return {"ticker": ticker, "rows_before": 0, "fixed": 0, "status": "no_data"}

    # Exclude Is_Stale forward-fill rows from correction logic: these carry the
    # previous session's close unchanged and would corrupt rolling-median references
    # (e.g. 63 stale rows at 5.56 in HAFR 2026 would mask the real 1.2 median).
    # Stale rows are preserved verbatim in the output.
    stale_col = "Is_Stale"
    if stale_col in df_full.columns:
        stale_mask = df_full[stale_col].astype(str).str.lower().isin({"true", "1", "yes"})
        df_stale = df_full[stale_mask]
        df = df_full[~stale_mask].copy()
    else:
        df_stale = pd.DataFrame()
        df = df_full.copy()

    rows_before = len(df)
    total_fixed = 0

    # Pass 1: small datasets — check for 100x errors using dataset median
    df, n = _fix_single_value_100x(df)
    total_fixed += n

    # Pass 2: year-level shifts (entire year 10x too high)
    df, n = _fix_year_shifts(df, ticker)
    total_fixed += n

    # Pass 3: within-year outliers where year median is correct but blocks
    #          of wrong values fool the rolling-median window (e.g. KCB 2007)
    df, n = _fix_within_year_outliers(df)
    total_fixed += n

    # Pass 4: remaining row-level spikes via rolling-median ratio
    df, n = _fix_row_spikes(df)
    total_fixed += n

    result = {
        "ticker": ticker,
        "rows_before": rows_before,
        "rows_after": len(df),
        "fixed": total_fixed,
        "status": "dry_run" if dry_run else ("changed" if total_fixed else "clean"),
    }

    if total_fixed and not dry_run:
        # Recombine corrected real rows with unchanged stale rows, restore sort order
        if not df_stale.empty:
            df_out = pd.concat([df, df_stale]).sort_index()
        else:
            df_out = df
        df_out.to_csv(csv_path)
        log.info(
            "%-16s  %d correction(s) — saved (%d→%d rows)",
            ticker, total_fixed, rows_before, len(df),
        )
    elif total_fixed:
        log.info("%-16s  %d correction(s) would be applied (dry-run)", ticker, total_fixed)
    else:
        log.debug("%-16s  clean", ticker)

    return result


# ── Main ───────────────────────────────────────────────────────────────────────

def main(
    dry_run: bool = False,
    ticker_filter: str | None = None,
    skip_tickers: set[str] | None = None,
) -> None:
    companies = load_companies()
    safe_set = {c["ticker"].replace(".", "_") for c in companies}
    skip_set = skip_tickers or set()

    paths = sorted(DATA_CLEANED.glob("*_cleaned.csv"))
    if ticker_filter:
        paths = [p for p in paths if p.stem.replace("_cleaned", "") == ticker_filter]
        if not paths:
            log.error("Ticker %s not found in data/cleaned/", ticker_filter)
            return

    results = []
    changed = []

    for path in paths:
        safe = path.stem.replace("_cleaned", "")
        if safe not in safe_set:
            continue
        if safe in skip_set:
            log.debug("%-16s  skipped (--skip)", safe)
            continue
        result = fix_ticker(path, dry_run=dry_run)
        results.append(result)
        if result["fixed"]:
            changed.append(result)

    print()
    print(f"{'Ticker':<18} {'Before':>6}  {'After':>6}  {'Fixed':>6}  Status")
    print("-" * 55)
    for r in results:
        if r["fixed"]:
            print(
                f"{r['ticker']:<18} {r.get('rows_before',0):>6}  "
                f"{r.get('rows_after',r.get('rows_before',0)):>6}  "
                f"{r['fixed']:>6}  {r['status']}"
            )

    print()
    print(f"Tickers with corrections: {len(changed)}")
    if skip_set:
        print(f"Skipped (need manual review): {', '.join(sorted(skip_set))}")
    if dry_run:
        print("(DRY RUN — no files written)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix decimal-point errors in cleaned CSVs")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write")
    parser.add_argument("--ticker", default=None, help="Process one ticker, e.g. EQTY_NR")
    parser.add_argument(
        "--skip",
        default=None,
        help="Comma-separated tickers to exclude, e.g. HAFR_NR,TOTL_NR",
    )
    args = parser.parse_args()
    skip = set(args.skip.split(",")) if args.skip else None
    main(dry_run=args.dry_run, ticker_filter=args.ticker, skip_tickers=skip)
