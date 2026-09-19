"""
Fill gaps in every company's price history by forward-filling the last known price.

Rule: NSE is open Mon–Fri. If a company has no record for a trading day between
its first listing date and today, carry forward the previous close (same OHLCV,
volume=0 since no trade occurred). This ensures charts show a flat line rather
than a gap.

Trading calendar: derived from the union of all dates across all company CSVs
(any day that appears in at least one CSV is a valid trading day).

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \\
    python pipeline/scripts/fill_missing_dates.py [--dry-run] [--ticker SCOM]
"""
import argparse
import datetime
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_CLEANED = REPO_ROOT / "data" / "cleaned"


def build_trading_calendar(csv_files: list[Path]) -> set[datetime.date]:
    """
    Union of all dates across every cleaned CSV = known NSE trading days.
    Any date present in at least one company's CSV is a valid trading day.
    """
    trading_days: set[datetime.date] = set()
    for f in csv_files:
        try:
            df = pd.read_csv(f, usecols=["Date"], parse_dates=["Date"])
            trading_days.update(d.date() for d in df["Date"] if pd.notna(d))
        except Exception:
            pass
    return trading_days


def fill_ticker(csv_path: Path, calendar: set[datetime.date], dry_run: bool) -> int:
    """
    Forward-fill missing trading days for one ticker.
    Returns number of rows added.
    """
    ticker = csv_path.stem.replace("_cleaned", "")
    df = pd.read_csv(csv_path, parse_dates=["Date"])

    stale_col = "Is_Stale" in df.columns
    if stale_col:
        active = df[df["Is_Stale"] == 0].copy()
    else:
        active = df.copy()

    if active.empty:
        return 0

    active = active.sort_values("Date").reset_index(drop=True)
    first_date = active["Date"].iloc[0].date()
    last_date = datetime.date.today()

    # All trading days this ticker should have data for
    expected_days = sorted(d for d in calendar if first_date <= d <= last_date)
    # Use ALL rows (stale and active) so we don't add forward-fills for stale-only dates
    existing_days = set(df["Date"].dt.date.tolist())
    missing_days = [d for d in expected_days if d not in existing_days]

    if not missing_days:
        return 0

    log.info("  %s: %d missing trading days — forward-filling", ticker, len(missing_days))

    if dry_run:
        sample = [str(d) for d in missing_days[:5]]
        log.info("  %s: sample missing: %s%s", ticker, sample, " ..." if len(missing_days) > 5 else "")
        return len(missing_days)

    # Build a map of date -> last known row for forward-fill
    all_dates = sorted(expected_days)
    last_row = None
    new_rows = []

    date_to_row = {r["Date"].date(): i for i, r in active.iterrows()}

    for d in all_dates:
        if d in date_to_row:
            last_row = active.iloc[date_to_row[d]].to_dict()
        elif last_row is not None and d in set(missing_days):
            # Carry forward — no trade happened, price unchanged, volume = 0
            row = dict(last_row)
            row["Date"] = pd.Timestamp(d)
            row["Volume"] = 0
            # Low = High = Open = Close (no price movement)
            row["Open"] = last_row["Close"]
            row["High"] = last_row["Close"]
            row["Low"] = last_row["Close"]
            if stale_col:
                row["Is_Stale"] = 0
            new_rows.append(row)

    if not new_rows:
        return 0

    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([df, new_df], ignore_index=True).sort_values("Date")
    combined.to_csv(csv_path, index=False)
    log.info("  %s: added %d rows", ticker, len(new_rows))
    return len(new_rows)


def push_to_rtdb(root_ref, csv_path: Path) -> int:
    """Re-push the full ticker CSV to RTDB via the single write choke point.

    Unlike the pre-2026-09-19 version, stale rows are NOT dropped — they're
    pushed with an explicit `filled: true` flag so the frontend can render
    'every trading day has a value' while still visually marking the
    synthetic rows so users know they weren't real trades.

    A row is treated as a forward-fill when either:
      * `Is_Stale == 1` in the CSV — the cleaner tagged it as no-real-trade
        (either the scraper produced 0-volume/duplicate values, or
        fill_missing_dates itself added it and the cleaner re-flagged it), or
      * volume == 0 AND open == close == high == low — the classic
        forward-fill shape regardless of the stale flag.
    """
    from pipeline.scripts.firebase_rtdb import bulk_write_prices

    ticker = csv_path.stem.replace("_cleaned", "")
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    # No longer filtering `Is_Stale == 1` — those rows carry the forward-fill
    # info we want to preserve. Dedup instead: prefer the real-volume row
    # (`Is_Stale=0`) when the same date has both.
    if "Is_Stale" in df.columns:
        df["_stale_sort"] = df["Is_Stale"].fillna(0).astype(int)
        df = df.sort_values(["Date", "_stale_sort"], ascending=[True, True])
        df = df.drop_duplicates(subset=["Date"], keep="first").drop(columns=["_stale_sort"])
    df = df.sort_values("Date").reset_index(drop=True)

    records: dict[str, dict] = {}
    for i, row in df.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d")
        close = float(row["Close"]) if pd.notna(row.get("Close")) else None
        open_ = float(row["Open"]) if pd.notna(row.get("Open")) else None
        high  = float(row["High"]) if pd.notna(row.get("High")) else None
        low   = float(row["Low"])  if pd.notna(row.get("Low"))  else None
        vol   = float(row["Volume"]) if pd.notna(row.get("Volume")) else None
        prev_close = (
            float(df.iloc[i - 1]["Close"])
            if i > 0 and pd.notna(df.iloc[i - 1]["Close"])
            else None
        )
        ch = (
            round(close - prev_close, 4)
            if close is not None and prev_close is not None
            else None
        )
        pch = (
            round((ch / prev_close) * 100, 4)
            if ch is not None and prev_close
            else None
        )
        is_stale = bool(row.get("Is_Stale")) if "Is_Stale" in row else False
        is_flat = (
            vol == 0 and close is not None and open_ is not None
            and high is not None and low is not None
            and close == open_ == high == low
        )
        filled = is_stale or is_flat
        records[date_str] = {
            "o": open_, "h": high, "l": low, "c": close, "v": vol,
            "pc": prev_close, "ch": ch, "pch": pch, "vv": None,
            "filled": filled,
        }
    return bulk_write_prices(root_ref, ticker, records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ticker", help="Process single ticker only")
    parser.add_argument("--csv-only", action="store_true", help="Fill CSVs but skip RTDB push")
    args = parser.parse_args()

    csv_files = sorted(DATA_CLEANED.glob("*_cleaned.csv"))
    if args.ticker:
        csv_files = [f for f in csv_files if args.ticker.upper() in f.stem.upper()]
    if not csv_files:
        log.error("No CSVs found in %s", DATA_CLEANED)
        sys.exit(1)

    log.info("Building trading calendar from %d CSVs...", len(csv_files))
    all_files = sorted(DATA_CLEANED.glob("*_cleaned.csv"))
    calendar = build_trading_calendar(all_files)
    log.info("Calendar has %d unique trading days (%s to %s)",
             len(calendar), min(calendar), max(calendar))

    root_ref = None
    if not args.dry_run and not args.csv_only:
        sys.path.insert(0, str(REPO_ROOT))
        from pipeline.scripts.firebase_client import get_rtdb
        root_ref = get_rtdb()

    total_added = 0
    tickers_fixed: list[str] = []

    for csv_path in csv_files:
        try:
            added = fill_ticker(csv_path, calendar, args.dry_run)
            if added > 0:
                total_added += added
                tickers_fixed.append(csv_path.stem.replace("_cleaned", ""))
                if not args.dry_run and root_ref is not None:
                    written = push_to_rtdb(root_ref, csv_path)
                    log.info("  %s: pushed %d RTDB nodes", csv_path.stem.replace("_cleaned", ""), written)
        except Exception as exc:
            log.error("  %s: FAILED — %s", csv_path.stem, exc, exc_info=True)

    log.info("=" * 60)
    log.info("Done — %d rows added across %d tickers", total_added, len(tickers_fixed))
    if tickers_fixed:
        log.info("Affected: %s", ", ".join(tickers_fixed))


if __name__ == "__main__":
    main()
