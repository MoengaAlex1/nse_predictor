"""
NSE Kenya Daily Data Scraper
----------------------------
Fetches end-of-day prices for all NSE-listed equities from the NSE live ticker API
and appends new rows to the local archive CSV.

Usage:
    python scripts/scrape_nse.py

Run daily after market close (EAT, GMT+3) — typically after 15:30.
"""

import sys
import json
import logging
from pathlib import Path
from datetime import date, datetime

import requests
import pandas as pd

# ── Config ────────────────────────────────────────────────────────────────────
ARCHIVE_DIR = Path(r"C:\Users\moeng\Downloads\archive")
TICKER_API  = "https://deveintapps.com/nseticker/api/v1/ticker"
API_PAYLOAD = {"nopage": "true", "isinno": "KE3000009674"}
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Referer": "https://www.nse.co.ke/equities-market/",
    "Origin": "https://www.nse.co.ke",
    "Host": "deveintapps.com",
}

# Canonical company name map (code → full name used in archive CSVs)
COMPANY_NAMES: dict[str, str] = {
    "ABSA": "ABSA Bank Kenya Ltd",
    "ALP":  "ALP Industrial REIT",
    "AMAC": "Africa Mega Agricorp Ltd",
    "ARM":  "ARM Cement Ltd",
    "BAMB": "Bamburi Cement Ltd Ord 5.00",
    "BAT":  "British American Tobacco Kenya Ltd Ord 10.00",
    "BKG":  "BK Group PLC",
    "BOC":  "BOC Kenya Ltd Ord 5.00",
    "BRIT": "Britam Holdings Ltd Ord 0.10",
    "CABL": "East African Cables Ltd Ord 0.50",
    "CARB": "Carbacid Investments Ltd Ord 5.00",
    "CGEN": "Centum Generation",
    "CIC":  "CIC Insurance Group Ltd Ord 1.00",
    "COOP": "Co-operative Bank of Kenya Ltd Ord 1.00",
    "CRWN": "Crown Paints Kenya Ltd Ord 5.00",
    "CTUM": "Cavendish & Hyde Ltd",
    "DCON": "Deacons East Africa Ltd",
    "DTK":  "Diamond Trust Bank Kenya Ltd Ord 4.00",
    "EABL": "East African Breweries Ltd Ord 2.00",
    "EGAD": "Eaagads Ltd Ord 1.25",
    "EQTY": "Equity Group Holdings Ltd Ord 0.50",
    "EVRD": "Eveready East Africa Ltd Ord 1.00",
    "FAHR": "Fahari Income REIT",
    "FMLY": "Family Bank Ltd Ord 5.00",
    "FTGH": "ILAM Fahari I-REIT",
    "GLD":  "Gold Coin Holdings Ltd",
    "HAFR": "Home Afrika Ltd Ord 0.50",
    "HBE":  "HBE Ltd",
    "HFCK": "HF Group Ltd Ord 5.00",
    "IMH":  "I&M Holdings Ltd Ord 1.00",
    "JUB":  "Jubilee Holdings Ltd Ord 1.00",
    "KAPC": "KAPS Medical International Ltd",
    "KCB":  "KCB Group Ltd Ord 1.00",
    "KEGN": "KenGen Company Ltd Ord 2.50",
    "KNRE": "Kenya Reinsurance Corporation Ltd Ord 2.50",
    "KPC":  "Kenya Power and Lighting Company Ltd Ord 20.00",
    "KPLC": "Kenya Power and Lighting Company Ltd Pref 20.00",
    "KQ":   "Kenya Airways Ltd Ord 5.00",
    "KUKZ": "Kakuzi Ltd Ord 5.00",
    "KURV": "Kurwitu Ventures Ltd",
    "LAPR": "Laptrust Imara I-REIT",
    "LBTY": "Liberty Kenya Holdings Ltd Ord 1.00",
    "LIMT": "Limuru Tea Company Ltd Ord 20.00",
    "LKL":  "Longhorn Publishers Ltd Ord 1.00",
    "MSC":  "Merchant Services Company Ltd",
    "NBK":  "National Bank of Kenya Ltd Ord 5.00",
    "NBV":  "Nairobi Business Ventures Ltd",
    "NCBA": "NCBA Group Ltd Ord 5.00",
    "NMG":  "Nation Media Group Ltd Ord 2.50",
    "NSE":  "Nairobi Securities Exchange Ltd Ord 4.00",
    "OCH":  "Olympia Capital Holdings Ltd Ord 5.00",
    "PORT": "East African Portland Cement Company Ltd Ord 5.00",
    "SASN": "Sasini Ltd Ord 1.00",
    "SBIC": "SBM Bank Kenya Ltd",
    "SCAN": "Scangroup Ltd Ord 1.00",
    "SCBK": "Standard Chartered Bank Kenya Ltd Ord 5.00",
    "SCOM": "Safaricom Ltd Ord 0.05",
    "SGL":  "Standard Group Ltd Ord 5.00",
    "SKL":  "Stanbic Holdings Ltd Ord 5.00",
    "SLAM": "Sanlam Kenya Ltd Ord 2.50",
    "SMER": "Sameer Africa Ltd Ord 5.00",
    "SMWF": "Stanlib Fahari I-REIT",
    "TCL":  "TransCentury Ltd Ord 1.00",
    "TOTL": "TotalEnergies EP Kenya Ltd Ord 5.00",
    "TPSE": "TransCentury Ltd",
    "TRFC": "Rift Valley Railways",
    "UCHM": "Unga Holdings Ltd",
    "UMME": "Umeme Ltd",
    "UNGA": "Unga Group Ltd Ord 5.00",
    "WTK":  "Williamson Tea Kenya Ltd Ord 5.00",
    "XPRS": "Expressa Ltd",
}

LOG_FMT = "%(asctime)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
log = logging.getLogger(__name__)


# ── Archive helpers ───────────────────────────────────────────────────────────

def _load_archive_for_12m(year: int) -> pd.DataFrame:
    """Return a date+code+close df from one archive year file."""
    path = ARCHIVE_DIR / f"NSE_data_all_stocks_{year}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        if "Code" not in df.columns or "Day Price" not in df.columns:
            return pd.DataFrame()
        df["_dt"] = pd.to_datetime(df["Date"].str.strip(), dayfirst=False, format="mixed", errors="coerce")
        df = df.dropna(subset=["_dt"])
        df["_close"] = pd.to_numeric(
            df["Day Price"].astype(str).str.replace(",", "").str.strip(), errors="coerce"
        )
        df["Code"] = df["Code"].str.strip()
        return df[["_dt", "Code", "_close"]].dropna(subset=["_close"])
    except Exception as e:
        log.warning("Could not load %s: %s", path.name, e)
        return pd.DataFrame()


def _build_12m_extremes(today: date) -> dict[str, tuple[float, float]]:
    """Return {code: (12m_low, 12m_high)} using the last 252 trading-day rows."""
    cutoff = pd.Timestamp(today) - pd.DateOffset(days=365)
    frames = []
    for yr in [today.year - 1, today.year]:
        f = _load_archive_for_12m(yr)
        if not f.empty:
            frames.append(f)
    if not frames:
        return {}
    hist = pd.concat(frames, ignore_index=True)
    hist = hist[hist["_dt"] >= cutoff]
    result: dict[str, tuple[float, float]] = {}
    for code, grp in hist.groupby("Code"):
        prices = grp["_close"].dropna()
        if len(prices) >= 5:
            result[code] = (round(float(prices.min()), 4), round(float(prices.max()), 4))
    return result


def _last_date_in_archive(year: int) -> date | None:
    """Return the latest date present in the archive file for `year`."""
    path = ARCHIVE_DIR / f"NSE_data_all_stocks_{year}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, dtype=str, usecols=lambda c: c.strip() == "Date")
        df.columns = [c.strip() for c in df.columns]
        dt = pd.to_datetime(df["Date"].str.strip(), dayfirst=False, format="mixed", errors="coerce").dropna()
        return dt.max().date() if not dt.empty else None
    except Exception:
        return None


# ── API fetch ─────────────────────────────────────────────────────────────────

def fetch_snapshot() -> tuple[list[dict], date]:
    """Call the NSE ticker API and return (snapshot_list, trade_date)."""
    resp = requests.post(TICKER_API, headers=API_HEADERS, json=API_PAYLOAD, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    snapshot: list[dict] = data["message"][0]["snapshot"]
    meta = data["message"][1]["updated_at"]
    # date format from API: "17/07/2026"
    trade_date = datetime.strptime(meta["date"], "%d/%m/%Y").date()
    log.info("API returned %d rows for %s (market: %s)",
             len(snapshot), trade_date, meta.get("market_status", "?"))
    return snapshot, trade_date


# ── Row builder ───────────────────────────────────────────────────────────────

def build_rows(snapshot: list[dict], trade_date: date,
               extremes: dict[str, tuple[float, float]]) -> list[dict]:
    """Convert API snapshot items to archive-format dicts, deduplicating by code+date."""
    seen: set[str] = set()
    rows: list[dict] = []
    date_str = trade_date.strftime("%-m/%-d/%Y") if sys.platform != "win32" else trade_date.strftime("%#m/%#d/%Y")

    for item in snapshot:
        code = item["issuer"]
        if code in seen:
            continue
        seen.add(code)

        price    = item.get("today_close") or item.get("price") or item.get("ltp")
        prev     = item.get("prev_price")
        high     = item.get("today_high")
        low      = item.get("today_low")
        volume   = item.get("volume")
        chg_pct  = item.get("change")     # already a percentage

        if price is None:
            continue

        price   = float(price)
        prev    = float(prev)   if prev   is not None else price
        high    = float(high)   if high   is not None else price
        low     = float(low)    if low    is not None else price
        volume  = int(volume)   if volume is not None else 0
        chg_pct = float(chg_pct) if chg_pct is not None else 0.0
        chg_abs = round(price - prev, 4)

        lo_12m, hi_12m = extremes.get(code, ("", ""))
        # Include today's price in 12m extremes
        if lo_12m != "":
            lo_12m = round(min(float(lo_12m), low), 4)
            hi_12m = round(max(float(hi_12m), high), 4)
        else:
            lo_12m = low
            hi_12m = high

        rows.append({
            "Date":           date_str,
            "Code":           code,
            "Name":           COMPANY_NAMES.get(code, code),
            "12m Low":        lo_12m,
            "12m High":       hi_12m,
            "Day Low":        low,
            "Day High":       high,
            "Day Price":      price,
            "Previous":       prev,
            "Change":         chg_abs,
            "Change%":        round(chg_pct, 4),
            "Volume":         volume,
            "Adjusted Price": price,
        })
    return rows


# ── Append to archive CSV ─────────────────────────────────────────────────────

ARCHIVE_COLS = [
    "Date", "Code", "Name", "12m Low", "12m High",
    "Day Low", "Day High", "Day Price", "Previous",
    "Change", "Change%", "Volume", "Adjusted Price",
]


def append_to_archive(rows: list[dict], trade_date: date) -> int:
    """Append new rows to the year-appropriate archive CSV. Returns row count written.

    If the destination file is locked, falls back to writing a sidecar patch file
    (NSE_patch_YYYY-MM-DD.csv) that can be merged later by the Dash app.
    """
    if not rows:
        return 0
    dest = ARCHIVE_DIR / f"NSE_data_all_stocks_{trade_date.year}.csv"
    new_df = pd.DataFrame(rows, columns=ARCHIVE_COLS)

    if dest.exists():
        try:
            existing = pd.read_csv(dest, dtype=str)
        except PermissionError:
            log.warning("Archive CSV locked — writing sidecar patch file instead.")
            patch = ARCHIVE_DIR / f"NSE_patch_{trade_date.isoformat()}.csv"
            new_df.to_csv(patch, index=False)
            log.info("Patch file written: %s (%d rows). Merge manually or re-run after closing the file.", patch.name, len(new_df))
            return len(new_df)

        existing.columns = [c.strip() for c in existing.columns]
        # Remove any existing rows for this date (idempotent)
        existing["_dt"] = pd.to_datetime(existing["Date"].str.strip(),
                                         dayfirst=False, format="mixed", errors="coerce")
        trade_ts = pd.Timestamp(trade_date)
        existing = existing[existing["_dt"] != trade_ts].drop(columns=["_dt"])
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    try:
        combined.to_csv(dest, index=False)
    except PermissionError:
        log.warning("Archive CSV locked for writing — saving patch file.")
        patch = ARCHIVE_DIR / f"NSE_patch_{trade_date.isoformat()}.csv"
        new_df.to_csv(patch, index=False)
        log.info("Patch file: %s (%d rows)", patch.name, len(new_df))
        return len(new_df)

    log.info("Wrote %d rows to %s", len(new_df), dest.name)
    return len(new_df)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    today = date.today()
    archive_year = today.year
    last_date = _last_date_in_archive(archive_year)
    log.info("Last date in archive: %s | Today: %s", last_date, today)

    if last_date is not None and last_date >= today:
        log.info("Archive already up to date — nothing to do.")
        return

    log.info("Fetching NSE snapshot from live ticker API…")
    snapshot, trade_date = fetch_snapshot()

    if last_date is not None and trade_date <= last_date:
        log.info("API returned date %s which is not newer than archive (%s) — skipping.",
                 trade_date, last_date)
        return

    log.info("Building 12-month price extremes from archive…")
    extremes = _build_12m_extremes(trade_date)

    rows = build_rows(snapshot, trade_date, extremes)
    log.info("Built %d rows for %s", len(rows), trade_date)

    written = append_to_archive(rows, trade_date)
    log.info("Done. %d new rows appended to archive.", written)


if __name__ == "__main__":
    main()
