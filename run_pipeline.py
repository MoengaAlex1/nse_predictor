"""
Fetch/load NSE tickers, clean each one, print quality reports,
and save cleaned CSVs to data/cleaned/.

Usage:
    # Load from CSV files in data/raw/ (primary NSE path)
    python run_pipeline.py

    # Download a non-NSE ticker via yfinance (for testing)
    python run_pipeline.py --tickers AAPL MSFT TSLA

    # Load a specific CSV for one NSE ticker
    python run_pipeline.py --tickers SCOM.NR --csv data/raw/safaricom.csv

NSE data source:
    Download historical CSV from https://www.nse.co.ke/trade-statistics/historical-data/
    Save to data/raw/SCOM_NR_raw.csv  (match the ticker name, dots replaced with underscores)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data.fetcher import fetch_nse_data, save_raw
from src.data.cleaner import clean_ohlcv, validate_ticker, save_cleaned
from config import NSE_TICKERS


def run(tickers: list = None, csv_path: str = None):
    tickers = tickers or NSE_TICKERS
    print(f"Processing {len(tickers)} ticker(s): {tickers}\n")

    results = {}
    for ticker in tickers:
        print(f"\n--- {ticker} ---")
        try:
            df = fetch_nse_data(ticker, csv_path=csv_path if len(tickers) == 1 else None)
            save_raw({ticker: df})
        except Exception as e:
            print(f"  [SKIP] Could not load {ticker}: {e}")
            continue

        try:
            cleaned_df, report = clean_ohlcv(df, ticker=ticker)
            valid = validate_ticker(cleaned_df, report)
            if valid:
                path = save_cleaned(cleaned_df, ticker)
                print(f"  Saved cleaned -> {path.name}")
            else:
                print(f"  [WARN] {ticker} failed validation — not saved for modelling")
            results[ticker] = {"df": cleaned_df, "report": report, "valid": valid}
        except Exception as e:
            print(f"  [ERROR] Cleaning {ticker}: {e}")

    if not results:
        print("\nNo tickers processed successfully.")
        print("\nTo use NSE Kenya data:")
        print("  1. Download CSV from https://www.nse.co.ke/trade-statistics/historical-data/")
        print("  2. Save to data/raw/<TICKER>_raw.csv  (e.g. data/raw/SCOM_NR_raw.csv)")
        print("  3. Re-run: python run_pipeline.py --tickers SCOM.NR")
        print("\nTo test with yfinance data (non-NSE):")
        print("  python run_pipeline.py --tickers AAPL MSFT")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NSE Data Pipeline")
    parser.add_argument("--tickers", nargs="+", default=None,
                        help="Ticker symbols (default: all NSE_TICKERS from config)")
    parser.add_argument("--csv", default=None,
                        help="Path to a single CSV file (used when one ticker specified)")
    args = parser.parse_args()
    run(args.tickers, args.csv)
