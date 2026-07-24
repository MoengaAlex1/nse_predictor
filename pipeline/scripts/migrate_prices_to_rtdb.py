"""
One-time migration: reads all cleaned CSVs and writes to Firebase RTDB.

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \
    python pipeline/scripts/migrate_prices_to_rtdb.py [--dry-run] [--ticker SCOM]

Idempotent: uses RTDB update() — never overwrites existing nodes.
"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT    = Path(__file__).parent.parent.parent
DATA_CLEANED = REPO_ROOT / "data" / "cleaned"


def build_records(df: pd.DataFrame, skip_stale: bool = False) -> dict:
    """Convert cleaned CSV DataFrame to {date_str: fields} dict."""
    if skip_stale and "Is_Stale" in df.columns:
        df = df[df["Is_Stale"] == 0]
    df = df.sort_values("Date").reset_index(drop=True)
    records: dict = {}
    for i, row in df.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d")
        close    = float(row["Close"]) if pd.notna(row["Close"]) else None
        prev_row = df.iloc[i - 1] if i > 0 else None
        pc       = float(prev_row["Close"]) if prev_row is not None and pd.notna(prev_row["Close"]) else None
        ch       = round(close - pc, 4) if close is not None and pc is not None else None
        pch      = round((ch / pc) * 100, 4) if ch is not None and pc and pc != 0 else None
        records[date_str] = {
            "o":   float(row["Open"])   if pd.notna(row.get("Open"))   else None,
            "h":   float(row["High"])   if pd.notna(row.get("High"))   else None,
            "l":   float(row["Low"])    if pd.notna(row.get("Low"))    else None,
            "c":   close,
            "v":   float(row["Volume"]) if pd.notna(row.get("Volume")) else None,
            "pc":  pc,
            "ch":  ch,
            "pch": pch,
            "vv":  None,
        }
    return records


def migrate_ticker(ticker: str, csv_path: Path, root_ref, dry_run: bool = False) -> int:
    from pipeline.scripts.firebase_rtdb import bulk_write_prices
    log.info("  %s: reading %s", ticker, csv_path.name)
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    if df.empty:
        log.warning("  %s: empty CSV, skipping", ticker)
        return 0
    records = build_records(df, skip_stale=True)
    log.info("  %s: %d records to write", ticker, len(records))
    if dry_run:
        log.info("  %s: dry-run — no writes", ticker)
        return len(records)
    written = bulk_write_prices(root_ref, ticker, records, batch_size=500)
    log.info("  %s: wrote %d nodes", ticker, written)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ticker", help="Migrate single ticker only")
    args = parser.parse_args()

    from pipeline.scripts.firebase_client import get_rtdb
    root_ref = get_rtdb()

    csv_files = sorted(DATA_CLEANED.glob("*_cleaned.csv"))
    if args.ticker:
        csv_files = [f for f in csv_files if args.ticker.upper() in f.name.upper()]
    if not csv_files:
        log.error("No CSVs found in %s", DATA_CLEANED)
        sys.exit(1)

    log.info("Migrating %d tickers to RTDB (dry_run=%s)", len(csv_files), args.dry_run)
    total = 0
    for csv_path in csv_files:
        ticker = csv_path.stem.replace("_cleaned", "")
        try:
            total += migrate_ticker(ticker, csv_path, root_ref, args.dry_run)
        except Exception as exc:
            log.error("  %s: FAILED — %s", ticker, exc)
    log.info("Done — %d total nodes written", total)


if __name__ == "__main__":
    main()
