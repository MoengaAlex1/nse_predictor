"""
scrape_nse_prices.py

Daily NSE price scraper with three-tier data source fallback:
  1. NSE website  — https://www.nse.co.ke/live-market-data/equity-securities.html
  2. stooq.com    — https://stooq.com/q/d/l/?s={ticker}.ke (reliable CSV API)
  3. Yahoo Finance — yfinance (.KE suffix) as last resort

For each company:
  1. Download the existing cleaned CSV from Firebase Storage.
     If not in Storage, seed from data/cleaned/ in the repo.
  2. Fetch any missing rows via the source chain above.
  3. Append new rows (dropping is_stale=1 and future dates), save, re-upload.

Usage:
  # Normal daily run (called by run_daily_update.py or directly):
  python pipeline/scripts/scrape_nse_prices.py

  # Backfill specific date range for all companies:
  python pipeline/scripts/scrape_nse_prices.py --backfill 2026-07-16:2026-07-20

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import logging
import os
import argparse
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import requests

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
_REQUIRED_COLS = {"Open", "High", "Low", "Close", "Volume"}

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nse.co.ke/",
}

# ── Ticker-name helpers ───────────────────────────────────────────────────────

def _safe_name(ticker: str) -> str:
    return ticker.replace(".", "_")


def _ticker_base(safe: str) -> str:
    """ABSA_NR → ABSA"""
    return safe[:-3] if safe.endswith("_NR") else safe


def _stooq_symbol(safe: str) -> str:
    """ABSA_NR → absa.ke"""
    return f"{_ticker_base(safe).lower()}.ke"


def _yf_symbol(safe: str) -> str:
    """ABSA_NR → ABSA.KE"""
    return f"{_ticker_base(safe)}.KE"


# ── Source 1: NSE website ─────────────────────────────────────────────────────

_nse_cache: dict[str, dict] | None = None  # keyed by uppercase symbol → {Close, Volume}

def _fetch_nse_website_all() -> dict[str, dict]:
    """
    Scrape the NSE equity securities page once per run.
    Returns {TICKER: {Close, Open, High, Low, Volume}} or {}.
    """
    global _nse_cache
    if _nse_cache is not None:
        return _nse_cache

    urls = [
        "https://www.nse.co.ke/live-market-data/equity-securities.html",
        "https://www.nse.co.ke/market-statistics/",
    ]
    results: dict[str, dict] = {}

    for url in urls:
        try:
            resp = requests.get(url, headers=_NSE_HEADERS, timeout=30)
            resp.raise_for_status()

            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                table = (
                    soup.find("table", {"id": "live-market"})
                    or soup.find("table", {"class": lambda c: c and "equity" in c.lower()})
                    or soup.find("table")
                )
                if not table:
                    continue

                rows = table.find_all("tr")
                header = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]

                # Locate column indices flexibly
                def _col(keywords: list[str]) -> int:
                    for kw in keywords:
                        for i, h in enumerate(header):
                            if kw in h:
                                return i
                    return -1

                idx_sym   = _col(["symbol", "share", "code", "ticker"])
                idx_close = _col(["last traded", "close", "price"])
                idx_vol   = _col(["volume", "vol"])
                idx_open  = _col(["open"])
                idx_high  = _col(["high"])
                idx_low   = _col(["low"])

                if idx_sym < 0 or idx_close < 0:
                    continue

                def _num(cells: list, idx: int) -> float | None:
                    if idx < 0 or idx >= len(cells):
                        return None
                    txt = cells[idx].get_text(strip=True).replace(",", "")
                    try:
                        return float(txt)
                    except ValueError:
                        return None

                for row in rows[1:]:
                    cells = row.find_all(["td", "th"])
                    if len(cells) <= max(idx_sym, idx_close):
                        continue
                    symbol = cells[idx_sym].get_text(strip=True).upper()
                    close  = _num(cells, idx_close)
                    if not symbol or close is None or close <= 0:
                        continue
                    results[symbol] = {
                        "Close":  close,
                        "Open":   _num(cells, idx_open)  or close,
                        "High":   _num(cells, idx_high)  or close,
                        "Low":    _num(cells, idx_low)   or close,
                        "Volume": int(_num(cells, idx_vol) or 0),
                    }

            except ImportError:
                log.debug("BeautifulSoup not available; skipping NSE HTML parse")

            if results:
                log.info("NSE website: fetched %d equity prices", len(results))
                break

        except Exception as exc:
            log.debug("NSE website fetch failed (%s) — trying next URL", exc)

    _nse_cache = results
    return results


def _fetch_nse_today(ticker_base: str) -> pd.DataFrame | None:
    """Return a one-row DataFrame with today's price from the NSE website, or None."""
    all_prices = _fetch_nse_website_all()
    row = all_prices.get(ticker_base.upper())
    if not row:
        return None

    today_ts = pd.Timestamp(TODAY)
    df = pd.DataFrame([row], index=pd.DatetimeIndex([today_ts], name="Date"))
    return df


# ── Source 2: stooq.com ───────────────────────────────────────────────────────

def _fetch_stooq(safe: str, from_date: str, to_date: str) -> pd.DataFrame | None:
    """
    Fetch OHLCV history from stooq.com for a date range.
    Returns DataFrame with DatetimeIndex or None.
    """
    symbol = _stooq_symbol(safe)
    d1 = from_date.replace("-", "")
    d2 = to_date.replace("-", "")
    url = f"https://stooq.com/q/d/l/?s={symbol}&d1={d1}&d2={d2}&i=d"

    try:
        resp = requests.get(url, headers=_NSE_HEADERS, timeout=20)
        if resp.status_code != 200:
            return None
        text = resp.text.strip()
        if not text or "No data" in text or len(text) < 30:
            return None

        df = pd.read_csv(StringIO(text))
        if df.empty or "Close" not in df.columns:
            return None

        df.columns = [c.strip().title() for c in df.columns]
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        df = df[df["Close"] > 0]
        return df if not df.empty else None

    except Exception as exc:
        log.debug("stooq fetch failed for %s: %s", symbol, exc)
        return None


# ── Source 3: yfinance ────────────────────────────────────────────────────────

def _fetch_yfinance(safe: str, period: str = "5d") -> pd.DataFrame | None:
    """Fetch recent OHLCV from Yahoo Finance. Returns DataFrame or None."""
    try:
        import yfinance as yf
        symbol = _yf_symbol(safe)
        raw = yf.download(symbol, period=period, auto_adjust=True, progress=False)
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw.index = pd.to_datetime(raw.index)
        raw.index.name = "Date"
        return raw if not raw.empty else None
    except Exception as exc:
        log.debug("yfinance fetch failed for %s: %s", safe, exc)
        return None


# ── Unified fetch ─────────────────────────────────────────────────────────────

def _fetch_new_rows(
    safe: str,
    last_known_date: pd.Timestamp | None,
    backfill_from: str | None = None,
    backfill_to: str | None = None,
) -> pd.DataFrame | None:
    """
    Fetch missing rows for `safe` ticker using the source chain.

    In backfill mode (backfill_from/to supplied), requests a full date range.
    In normal mode, fetches recent data and filters to rows after last_known_date.
    """
    ticker_base = _ticker_base(safe)
    today_str = TODAY

    if backfill_from and backfill_to:
        # ── Backfill: stooq → yfinance (NSE website won't have historical)
        df = _fetch_stooq(safe, backfill_from, backfill_to)
        if df is None or df.empty:
            log.info("%s: stooq empty for backfill — trying yfinance", safe)
            df = _fetch_yfinance(safe, period="1mo")
            if df is not None and not df.empty:
                start = pd.Timestamp(backfill_from)
                end   = pd.Timestamp(backfill_to)
                df = df[(df.index >= start) & (df.index <= end)]
    else:
        # ── Normal daily: try today via NSE website first
        df = _fetch_nse_today(ticker_base)

        # If NSE website failed or stale, use stooq for last 7 days
        if df is None or df.empty:
            week_ago = (date.today() - timedelta(days=7)).isoformat()
            df = _fetch_stooq(safe, week_ago, today_str)

        # Last resort: yfinance 5-day window
        if df is None or df.empty:
            log.info("%s: stooq/NSE failed — falling back to yfinance", safe)
            df = _fetch_yfinance(safe, period="5d")

    if df is None or df.empty:
        return None

    # Keep only columns we care about
    keep = [c for c in _REQUIRED_COLS if c in df.columns]
    if "Close" not in keep:
        return None
    df = df[keep].copy()

    # Remove weekend rows (NSE only trades Mon-Fri)
    df = df[df.index.dayofweek < 5]

    # Remove future rows
    df = df[df.index <= pd.Timestamp(today_str)]

    # In normal mode, filter to only rows newer than what we already have
    if last_known_date is not None and not (backfill_from and backfill_to):
        df = df[df.index > last_known_date]

    return df if not df.empty else None


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _load_local_csv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            return None
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, format="mixed")
        df = df.set_index(date_col).sort_index()
        df.index.name = "Date"
        return df
    except Exception as exc:
        log.warning("Could not load %s: %s", path, exc)
        return None


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    """Drop stale/future rows and deduplicate."""
    today_ts = pd.Timestamp(date.today())
    if "Is_Stale" in df.columns:
        df = df[df["Is_Stale"] != 1]
    df = df[df.index <= today_ts]
    df = df[df.index.dayofweek < 5]
    df = df[~df.index.duplicated(keep="last")]
    return df.sort_index()


# ── Per-company scrape ────────────────────────────────────────────────────────

def scrape_company(
    company: dict,
    backfill_from: str | None = None,
    backfill_to: str | None = None,
) -> dict:
    """
    Download, update, and re-upload the cleaned CSV for one company.

    Returns {"ticker": safe, "scraped": bool, "date": str, "close": float | None}
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

    # 1. Get latest CSV from Storage (fallback: repo copy)
    in_storage = download_model_from_storage(storage_path, str(local_path))
    if not in_storage:
        repo_csv = PIPELINE_ROOT.parent / "data" / "cleaned" / f"{safe}_cleaned.csv"
        if repo_csv.exists():
            import shutil
            CSVS_TMP.mkdir(parents=True, exist_ok=True)
            shutil.copy2(repo_csv, local_path)
            log.info("%s: seeded from repo CSV", safe)

    # 2. Load existing data
    existing_df: pd.DataFrame | None = None
    if local_path.exists():
        existing_df = _load_local_csv(local_path)
        if existing_df is not None:
            existing_df = _clean_df(existing_df)

    last_known = existing_df.index.max() if (existing_df is not None and not existing_df.empty) else None

    # 3. Fetch new rows
    new_rows = _fetch_new_rows(safe, last_known, backfill_from, backfill_to)

    if new_rows is None or new_rows.empty:
        if last_known is not None:
            log.info("%s: already up to date (latest: %s)", safe, last_known.date())
        else:
            log.warning("%s: no data found from any source", safe)
        return result

    # 4. Merge existing + new
    if existing_df is not None and not existing_df.empty:
        keep_cols = [c for c in new_rows.columns if c in existing_df.columns or c in _REQUIRED_COLS]
        existing_sub = existing_df[[c for c in keep_cols if c in existing_df.columns]]
        combined = pd.concat([existing_sub, new_rows[keep_cols]]).sort_index()
    else:
        combined = new_rows.sort_index()

    combined = combined[~combined.index.duplicated(keep="last")]
    combined = _clean_df(combined)

    # 5. Save and upload
    CSVS_TMP.mkdir(parents=True, exist_ok=True)
    combined.to_csv(local_path)
    upload_model_to_storage(str(local_path), storage_path)

    latest_date  = new_rows.index.max()
    latest_close = float(new_rows["Close"].iloc[-1])

    log.info(
        "%-20s  appended %d row(s) up to %s  close=%.4f  source=%s",
        safe,
        len(new_rows),
        latest_date.date(),
        latest_close,
        "NSE/stooq/yf",
    )

    result["scraped"] = True
    result["date"]    = latest_date.date().isoformat()
    result["close"]   = latest_close
    return result


# ── Batch main ────────────────────────────────────────────────────────────────

def main(
    backfill_from: str | None = None,
    backfill_to: str | None = None,
) -> dict[str, dict]:
    """
    Scrape all companies. In backfill mode supply from/to date strings (YYYY-MM-DD).
    Returns {safe_ticker: result_dict}.
    """
    CSVS_TMP.mkdir(parents=True, exist_ok=True)
    get_db()

    companies = load_companies()

    ticker_filter = os.environ.get("NSE_TICKERS_FILTER", "").strip()
    if ticker_filter:
        allowed = {t.strip().upper() for t in ticker_filter.split(",") if t.strip()}
        companies = [c for c in companies if c["ticker"].upper() in allowed]
        log.info("NSE_TICKERS_FILTER: scraping %d companies: %s", len(companies), ", ".join(allowed))

    if backfill_from:
        log.info("BACKFILL MODE: %s → %s for %d companies", backfill_from, backfill_to, len(companies))
    else:
        log.info("Scraping %d companies (NSE → stooq → yfinance)...", len(companies))

    results: dict[str, dict] = {}
    scraped_count = 0

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(scrape_company, c, backfill_from, backfill_to): c
            for c in companies
        }
        for fut in as_completed(futures):
            company = futures[fut]
            safe = _safe_name(company["ticker"])
            try:
                res = fut.result()
            except Exception as exc:
                log.error("Unexpected error scraping %s: %s", safe, exc, exc_info=True)
                res = {"ticker": safe, "scraped": False, "date": TODAY, "close": None}
            results[res["ticker"]] = res
            if res["scraped"]:
                scraped_count += 1

    log.info("Scraping complete: %d/%d companies updated.", scraped_count, len(companies))
    return results


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSE price scraper")
    parser.add_argument(
        "--backfill",
        metavar="FROM:TO",
        help="Backfill date range, e.g. 2026-07-16:2026-07-17",
    )
    args = parser.parse_args()

    bf_from = bf_to = None
    if args.backfill:
        parts = args.backfill.split(":")
        if len(parts) == 2:
            bf_from, bf_to = parts[0].strip(), parts[1].strip()
        else:
            parser.error("--backfill must be FROM:TO, e.g. 2026-07-16:2026-07-17")

    main(backfill_from=bf_from, backfill_to=bf_to)
