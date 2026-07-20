"""
Loader for the NSE archive CSV format.
Each yearly file contains all stocks with columns:
  Date, Code, Name, 12m Low, 12m High, Day Low, Day High,
  Day Price, Previous, Change, Change%, Volume, Adjusted Price

Maps to OHLCV as:
  Open  <- Previous (prior close = opening reference)
  High  <- Day High
  Low   <- Day Low
  Close <- Day Price
  Volume <- Volume
"""
import os
import re
import glob
import pandas as pd
import numpy as np
from pathlib import Path
from config import DATA_RAW, NSE_TICKERS, START_DATE

# Internal codes (no .NR suffix)
_CODE_MAP = {
    "SCOM.NR": "SCOM",
    "EQTY.NR": "EQTY",
    "KCB.NR":  "KCB",
    "EABL.NR": "EABL",
    "COOP.NR": "COOP",
    "BAMB.NR": "BAMB",
    "NMG.NR":  "NMG",
}

NSE_ARCHIVE_DIR = Path(os.environ.get("NSE_ARCHIVE_DIR", str(Path.home() / "Downloads" / "archive")))


def _clean_numeric(series: pd.Series) -> pd.Series:
    """Convert NSE numeric strings ('-', '1,234.56', '8.24%') to float."""
    s = series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False).str.strip()
    s = s.replace(["-", "", "nan", "NaN", "N/A"], np.nan)
    return pd.to_numeric(s, errors="coerce")


def load_nse_ticker(
    ticker: str,
    archive_dir: Path = NSE_ARCHIVE_DIR,
    start: str = START_DATE,
    end: str = None,
) -> pd.DataFrame:
    """
    Load full OHLCV history for a single NSE ticker from the yearly CSV archive.

    Parameters
    ----------
    ticker : str
        NSE ticker in either form — 'SCOM' or 'SCOM.NR'
    archive_dir : Path
        Directory containing NSE_data_all_stocks_YYYY.csv files
    start, end : str
        Date range filter (YYYY-MM-DD)
    """
    # Normalise ticker to internal code
    code = _CODE_MAP.get(ticker.upper(), ticker.upper().replace(".NR", ""))

    csv_files = sorted(glob.glob(str(archive_dir / "NSE_data_all_stocks_20*.csv")))
    if not csv_files:
        raise FileNotFoundError(f"No NSE archive CSVs found in {archive_dir}")

    frames = []
    for path in csv_files:
        try:
            df = pd.read_csv(path, dtype=str)
            # Normalise column names: pre-2022 files use ALL CAPS headers
            df.columns = [c.strip().title() for c in df.columns]
            # Rename variant column names to canonical form
            df = df.rename(columns={"Date": "Date", "Code": "Code", "Adjust": "Adjusted Price"})
            if "Code" not in df.columns:
                continue
            stock = df[df["Code"].str.strip() == code]
            if stock.empty:
                continue
            frames.append(stock)
        except Exception as e:
            print(f"  [WARN] Could not read {Path(path).name}: {e}")

    if not frames:
        raise ValueError(
            f"Ticker '{code}' not found in any NSE archive CSV.\n"
            f"Available codes: run list_nse_codes() to check."
        )

    combined = pd.concat(frames, ignore_index=True)

    # Parse date — formats seen: "2-Jan-24", "02-Jan-2024", "2024-01-02"
    combined["Date"] = pd.to_datetime(combined["Date"].str.strip(), dayfirst=True, format="mixed")
    combined = combined.sort_values("Date").drop_duplicates("Date").set_index("Date")

    # Build OHLCV
    out = pd.DataFrame(index=combined.index)
    out["Open"]   = _clean_numeric(combined["Previous"])   # prior close = open reference
    out["High"]   = _clean_numeric(combined["Day High"])
    out["Low"]    = _clean_numeric(combined["Day Low"])
    out["Close"]  = _clean_numeric(combined["Day Price"])
    out["Volume"] = _clean_numeric(combined["Volume"])
    out["Ticker"] = ticker

    # Drop rows where Close is NaN (suspended / no trade)
    out = out.dropna(subset=["Close"])

    # Apply date filters
    if start:
        out = out[out.index >= pd.to_datetime(start)]
    if end:
        out = out[out.index <= pd.to_datetime(end)]

    if out.empty:
        raise ValueError(f"No data for {code} after filtering to {start}–{end}")

    print(f"  Loaded {code}: {len(out)} trading days ({out.index[0].date()} to {out.index[-1].date()})")
    return out


def list_nse_codes(archive_dir: Path = NSE_ARCHIVE_DIR, year: int = 2024) -> list:
    """Return all stock codes available in the archive for a given year."""
    path = archive_dir / f"NSE_data_all_stocks_{year}.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path, dtype=str)
    return sorted(df["Code"].str.strip().unique().tolist())


def load_all_nse_tickers(
    tickers: list = None,
    archive_dir: Path = NSE_ARCHIVE_DIR,
    start: str = START_DATE,
) -> dict:
    """Load OHLCV for all specified NSE tickers from the archive."""
    if tickers is None:
        tickers = NSE_TICKERS
    data = {}
    for ticker in tickers:
        try:
            df = load_nse_ticker(ticker, archive_dir=archive_dir, start=start)
            data[ticker] = df
        except Exception as e:
            print(f"  [FAIL] {ticker}: {e}")
    return data
