"""
Data acquisition for NSE stocks.

Yahoo Finance does not carry NSE Nairobi (.NR) tickers directly.
Primary path: load from a CSV file downloaded from nse.co.ke or investing.com.
Fallback path: any yfinance-supported ticker (useful for testing / demo).

CSV format expected (nse.co.ke export):
    Date, Open, High, Low, Close, Volume
    (comma-separated, Date in YYYY-MM-DD or DD/MM/YYYY)
"""
import sys
import io
import logging
import yfinance as yf
import pandas as pd
from pathlib import Path
from config import NSE_TICKERS, START_DATE, DATA_RAW, DATA_CLEANED

log = logging.getLogger(__name__)

# Force UTF-8 output on Windows to avoid cp1252 encode errors
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── CSV loader (primary NSE path) ─────────────────────────────────────────

def load_from_csv(path: str | Path, ticker: str = "") -> pd.DataFrame:
    """
    Load OHLCV data from a CSV file (NSE website or investing.com export).
    Handles DD/MM/YYYY and YYYY-MM-DD date formats automatically.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    df = pd.read_csv(path)
    df.columns = [c.strip().title() for c in df.columns]

    # Find the date column
    date_col = next((c for c in df.columns if "date" in c.lower()), None)
    if date_col is None:
        raise ValueError("No date column found in CSV")

    df[date_col] = pd.to_datetime(df[date_col], dayfirst=False, format="mixed")
    df = df.set_index(date_col)
    df.index.name = "Date"
    df = df.sort_index()

    if ticker:
        df["Ticker"] = ticker
    return df


# ── yfinance loader (demo / non-NSE tickers) ──────────────────────────────

def fetch_yfinance(ticker: str, start: str = START_DATE, end: str = None) -> pd.DataFrame:
    """
    Fetch OHLCV from Yahoo Finance. Works for any supported ticker (not NSE .NR).
    Useful for testing the full pipeline with e.g. 'AAPL', 'MSFT', 'EQTY.KE'.
    """
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(
            f"No data returned for '{ticker}' from Yahoo Finance.\n"
            f"NOTE: NSE Nairobi (.NR) tickers are not on Yahoo Finance.\n"
            f"Use load_from_csv() with a file from nse.co.ke or investing.com instead."
        )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df["Ticker"] = ticker
    return df


# ── Smart fetcher (tries CSV first, then yfinance) ────────────────────────

def fetch_nse_data(
    ticker: str,
    start: str = START_DATE,
    end: str = None,
    csv_path: str | Path = None,
) -> pd.DataFrame:
    """
    Unified fetcher:
    1. If csv_path is provided, load from CSV.
    2. If a matching CSV exists in data/raw/, load it.
    3. Otherwise try yfinance (works for non-NSE tickers).
    """
    # Explicit CSV path
    if csv_path:
        df = load_from_csv(csv_path, ticker=ticker)
        if start:
            df = df[df.index >= pd.to_datetime(start)]
        return df

    # Auto-detect CSV in data/raw/
    safe_name = ticker.replace(".", "_")
    auto_csv = DATA_RAW / f"{safe_name}_raw.csv"
    if auto_csv.exists():
        log.info("Loading from cached CSV: %s", auto_csv.name)
        df = load_from_csv(auto_csv, ticker=ticker)
        if start:
            df = df[df.index >= pd.to_datetime(start)]
        return df

    # For .NR tickers, try the bundled NSE archive loader first
    if ticker.endswith(".NR"):
        try:
            from src.data.nse_loader import load_nse_ticker, NSE_ARCHIVE_DIR
            if NSE_ARCHIVE_DIR.exists():
                df = load_nse_ticker(ticker, start=start, end=end)
                return df
        except Exception as e:
            log.warning("NSE archive loader failed (%s); trying CSV fallback...", e)

        # Try pre-cleaned CSVs committed to the repo (53 companies included)
        cleaned_csv = DATA_CLEANED / f"{safe_name}_cleaned.csv"
        if cleaned_csv.exists():
            log.info("Loading from cleaned CSV: %s", cleaned_csv.name)
            df = load_from_csv(cleaned_csv, ticker=ticker)
            if start:
                df = df[df.index >= pd.to_datetime(start)]
            return df

        raise ValueError(
            f"NSE ticker '{ticker}': no data source found.\n"
            f"Checked: data/raw/{safe_name}_raw.csv, data/cleaned/{safe_name}_cleaned.csv\n"
            f"Or pass csv_path=... when calling fetch_nse_data()."
        )

    # Non-NSE ticker: use yfinance
    return fetch_yfinance(ticker, start=start, end=end)


def fetch_all_tickers(tickers: list = None, start: str = START_DATE) -> dict:
    if tickers is None:
        tickers = NSE_TICKERS
    data = {}
    for ticker in tickers:
        try:
            df = fetch_nse_data(ticker, start=start)
            data[ticker] = df
            log.info("[OK] %s: %d rows", ticker, len(df))
        except Exception as e:
            log.error("[FAIL] %s: %s", ticker, e)
    return data


def save_raw(data: dict) -> None:
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    for ticker, df in data.items():
        path = DATA_RAW / f"{ticker.replace('.', '_')}_raw.csv"
        df.to_csv(path)
        log.info("Saved raw -> %s", path.name)
