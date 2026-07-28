"""
backfill_prices.py

Backfills daily price data for specific NSE tickers using the afx.kwayisi.org
individual stock history pages (last ~10 trading days of real OHLCV data).
Works directly with local data/cleaned/ CSVs — no Firebase Storage required.
Also updates Firestore company documents via Firebase CLI OAuth token.

What this does:
  - Fetches the last ~10 trading days from afx.kwayisi.org/{ticker}/
  - Replaces Is_Stale rows with real data where afx has it
  - Appends new trading days not yet in the CSV
  - Updates Firestore companies/{TICKER} with current_price / price_preview

Usage:
    python pipeline/scripts/backfill_prices.py
    python pipeline/scripts/backfill_prices.py --tickers SCOM_NR NSE_NR
    python pipeline/scripts/backfill_prices.py --dry-run
    python pipeline/scripts/backfill_prices.py --skip-firestore
"""
import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup, NavigableString

PIPELINE_ROOT = Path(__file__).parent.parent
REPO_ROOT = PIPELINE_ROOT.parent
DATA_CLEANED = REPO_ROOT / "data" / "cleaned"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()
PROJECT_ID = "nse-market-dashboard"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    "/databases/(default)/documents"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}

DEFAULT_TICKERS = ["SCOM_NR", "NSE_NR", "TRFC_NR", "ALP_NR", "KURV_NR"]


# ── Ticker helpers ────────────────────────────────────────────────────────────

def _ticker_base(safe: str) -> str:
    return safe[:-3] if safe.endswith("_NR") else safe


def _afx_symbol(safe: str) -> str:
    return _ticker_base(safe).lower()


# ── afx individual stock page scraper ─────────────────────────────────────────

def _direct_text(tag: Any) -> str:
    """Get only direct NavigableString children (skip nested tags)."""
    return "".join(str(s) for s in tag.children if isinstance(s, NavigableString)).strip()


def _parse_volume(text: str) -> int:
    """Parse volume from afx (may have commas, may be trade count not share count)."""
    try:
        return int(float(text.replace(",", "")))
    except (ValueError, TypeError):
        return 0


def _parse_price(text: str) -> float | None:
    """Parse price from afx, stripping change suffix (+0.10+0.28%...)."""
    # The direct text of the close cell sometimes contains trailing change data
    # because afx nests: close_td > change_td > changepct_td. Direct text of
    # close_td gives only the close price itself (no nested content).
    try:
        return float(text.replace(",", ""))
    except (ValueError, TypeError):
        return None


def fetch_afx_history(safe: str) -> pd.DataFrame | None:
    """
    Scrape https://afx.kwayisi.org/nse/{symbol}/ for the historical price table.

    The afx individual stock page has a table with Date | Volume | Close | Change | Change%.
    Uses unclosed <td> tags (same structure as the main listing page) — navigate
    with direct-child traversal and _direct_text.

    Returns a DataFrame with DatetimeIndex and columns [Open, High, Low, Close, Volume]
    or None if no data is found.
    """
    symbol = _afx_symbol(safe)
    url = f"https://afx.kwayisi.org/nse/{symbol}/"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("afx history fetch failed for %s: %s", safe, exc)
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table")

    # Find the history table — first one whose header row contains "Date"
    hist_table = None
    for t in tables:
        header = t.find("tr")
        if header and "date" in header.get_text(strip=True).lower():
            hist_table = t
            break

    if hist_table is None:
        log.warning("afx: no history table found for %s", safe)
        return None

    rows_data = []
    for row in hist_table.find_all("tr")[1:]:  # skip header
        # Navigate the nested td chain: date → vol → close → change → changepct
        date_td = row.find("td", recursive=False)
        if not date_td:
            continue
        date_text = _direct_text(date_td)
        if not date_text or len(date_text) != 10:  # expect YYYY-MM-DD
            continue

        vol_td = date_td.find("td", recursive=False)
        if not vol_td:
            continue
        vol_text = _direct_text(vol_td)

        close_td = vol_td.find("td", recursive=False)
        if not close_td:
            continue
        close_text = _direct_text(close_td)

        # Parse
        try:
            trade_date = pd.Timestamp(date_text)
        except Exception:
            continue

        close = _parse_price(close_text)
        if close is None or close <= 0:
            continue

        volume = _parse_volume(vol_text)

        rows_data.append({
            "Date": trade_date,
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": volume,
            "Ticker": _ticker_base(safe),
        })

    if not rows_data:
        log.info("afx: no rows parsed for %s", safe)
        return None

    df = pd.DataFrame(rows_data).set_index("Date").sort_index()
    df = df[df.index.dayofweek < 5]  # trading days only
    df = df[df.index <= pd.Timestamp(TODAY)]
    log.info("afx history: %d rows for %s (latest=%s)", len(df), safe,
             df.index.max().date() if not df.empty else "n/a")
    return df if not df.empty else None


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _load_csv_all(safe: str) -> pd.DataFrame | None:
    """Load entire CSV including stale rows, preserving all columns."""
    path = DATA_CLEANED / f"{safe}_cleaned.csv"
    if not path.exists():
        log.warning("CSV not found: %s", path)
        return None
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if c.lower() == "date"), None)
        if date_col is None:
            return None
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=False, format="mixed")
        df = df.set_index(date_col).sort_index()
        df.index.name = "Date"
        df = df[df.index.dayofweek < 5]
        return df[~df.index.duplicated(keep="last")].sort_index()
    except Exception as exc:
        log.error("Failed to load %s: %s", safe, exc)
        return None


def _last_real_price(df: pd.DataFrame) -> tuple[pd.Timestamp | None, float | None]:
    """Return (date, price) of the last non-stale row."""
    if df is None or df.empty:
        return None, None
    real = df[df.get("Is_Stale", pd.Series(0, index=df.index)) != 1]
    if real.empty:
        real = df
    return real.index.max(), float(real["Close"].iloc[-1])


def _merge_with_real(existing: pd.DataFrame | None, new_rows: pd.DataFrame) -> pd.DataFrame:
    """
    Merge existing CSV data with new real-trade rows from afx.

    Strategy:
      - For dates in new_rows: use the new (real) data regardless of existing
        (replaces stale rows and corrects any wrong stale prices)
      - For dates not in new_rows: keep existing rows as-is
    """
    new_rows = new_rows.copy()
    new_rows["Is_Stale"] = 0

    if existing is None or existing.empty:
        return new_rows

    # Keep existing rows for dates NOT covered by new_rows
    existing_other = existing[~existing.index.isin(new_rows.index)]

    # Align columns: ensure both have the same columns before concat
    all_cols = list(dict.fromkeys(list(existing_other.columns) + list(new_rows.columns)))
    for col in all_cols:
        if col not in existing_other.columns:
            existing_other = existing_other.copy()
            existing_other[col] = None
        if col not in new_rows.columns:
            new_rows[col] = None

    combined = pd.concat([existing_other[all_cols], new_rows[all_cols]]).sort_index()
    return combined[~combined.index.duplicated(keep="last")].sort_index()


def _save_csv(safe: str, df: pd.DataFrame) -> None:
    path = DATA_CLEANED / f"{safe}_cleaned.csv"
    df.to_csv(path)
    log.info("Saved %d rows to %s", len(df), path.name)


# ── Per-ticker backfill ───────────────────────────────────────────────────────

def backfill_ticker(safe: str, dry_run: bool = False) -> dict:
    log.info("=== %s ===", safe)

    existing = _load_csv_all(safe)
    last_date, last_price = _last_real_price(existing)
    existing_count = len(existing) if existing is not None else 0

    log.info("%s: existing rows=%d, last_real_date=%s, last_real_price=%s",
             safe, existing_count, last_date, last_price)

    # Fetch afx history (~10 trading days)
    new_rows = fetch_afx_history(safe)

    if new_rows is None or new_rows.empty:
        log.info("%s: no new data from afx — reporting current state", safe)
        price_preview = []
        if existing is not None and not existing.empty:
            real = existing[existing.get("Is_Stale", pd.Series(0, index=existing.index)) != 1]
            price_preview = real["Close"].iloc[-30:].tolist() if not real.empty else []
        return {
            "ticker": safe,
            "rows_added": 0,
            "rows_updated": 0,
            "total_rows": existing_count,
            "last_date": str(last_date.date()) if last_date else "N/A",
            "last_price": last_price,
            "price_preview": price_preview,
            "change_pct_today": None,
        }

    # Count what will change
    if existing is not None:
        dates_new = set(new_rows.index) - set(existing.index)
        stale_mask = existing.get("Is_Stale", pd.Series(0, index=existing.index)) == 1
        dates_replacing_stale = set(new_rows.index) & set(existing[stale_mask].index)
    else:
        dates_new = set(new_rows.index)
        dates_replacing_stale = set()

    log.info("%s: %d new dates, %d stale rows to replace",
             safe, len(dates_new), len(dates_replacing_stale))

    merged = _merge_with_real(existing, new_rows)
    final_last_date = merged.index.max()
    final_last_price = float(merged.loc[merged.index.max(), "Close"])

    # Build price_preview from last 30 real (non-stale) rows
    real_rows = merged[merged.get("Is_Stale", pd.Series(0, index=merged.index)) != 1]
    price_preview = real_rows["Close"].iloc[-30:].tolist()
    change_pct = _compute_change_pct(real_rows)

    log.info("%s: merged to %d rows, last=%s, close=%.4f",
             safe, len(merged), final_last_date.date(), final_last_price)

    if not dry_run:
        _save_csv(safe, merged)

    return {
        "ticker": safe,
        "rows_added": len(dates_new),
        "rows_updated": len(dates_replacing_stale),
        "total_rows": len(merged),
        "last_date": str(final_last_date.date()),
        "last_price": final_last_price,
        "price_preview": price_preview,
        "change_pct_today": change_pct,
    }


def _compute_change_pct(df: pd.DataFrame) -> float | None:
    if len(df) < 2:
        return None
    prev = float(df["Close"].iloc[-2])
    curr = float(df["Close"].iloc[-1])
    if prev == 0:
        return None
    return round((curr - prev) / prev * 100, 4)


# ── Firestore REST helpers ─────────────────────────────────────────────────────

def _get_access_token() -> str | None:
    config = Path.home() / ".config" / "configstore" / "firebase-tools.json"
    if not config.exists():
        log.warning("Firebase CLI config not found at %s", config)
        return None
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
        token = data.get("tokens", {}).get("access_token", "")
        return token if token else None
    except Exception as exc:
        log.warning("Could not read Firebase CLI token: %s", exc)
        return None


def _to_firestore(value: Any) -> dict:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_to_firestore(v) for v in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {k: _to_firestore(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


def update_firestore_company(token: str, short_ticker: str, result: dict, dry_run: bool) -> bool:
    """PATCH companies/{ticker} with latest price data via Firestore REST API."""
    if result.get("last_price") is None:
        log.info("Skipping Firestore update for %s — no price data", short_ticker)
        return False

    update_fields = {
        "current_price": result["last_price"],
        "price_preview": result.get("price_preview", []),
        "price_date": result["last_date"],
        "last_updated": TODAY,
    }
    if result.get("change_pct_today") is not None:
        update_fields["change_pct_today"] = result["change_pct_today"]

    if dry_run:
        log.info("[DRY RUN] Would PATCH companies/%s: price=%.4f date=%s preview=%d items",
                 short_ticker, result["last_price"], result["last_date"],
                 len(result.get("price_preview", [])))
        return True

    mask_params = "&updateMask.fieldPaths=".join(update_fields.keys())
    url = f"{FIRESTORE_BASE}/companies/{short_ticker}?updateMask.fieldPaths={mask_params}"
    try:
        resp = requests.patch(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"fields": {k: _to_firestore(v) for k, v in update_fields.items()}},
            timeout=30,
        )
        if resp.status_code == 200:
            log.info("Firestore updated: companies/%s — price=%.4f date=%s",
                     short_ticker, result["last_price"], result["last_date"])
            return True
        else:
            log.warning("Firestore PATCH failed for %s: HTTP %d — %s",
                        short_ticker, resp.status_code, resp.text[:300])
            return False
    except Exception as exc:
        log.error("Firestore update error for %s: %s", short_ticker, exc)
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill NSE prices via afx.kwayisi.org history")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_TICKERS,
                        help="Safe ticker names, e.g. SCOM_NR NSE_NR")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and report without writing CSVs or Firestore")
    parser.add_argument("--skip-firestore", action="store_true",
                        help="Only update local CSVs, skip Firestore")
    args = parser.parse_args()

    log.info("=== NSE Price Backfill via afx.kwayisi.org | date=%s | tickers: %s ===",
             TODAY, ", ".join(args.tickers))
    if args.dry_run:
        log.info("DRY RUN — no files or Firestore will be written")

    token = None
    if not args.skip_firestore:
        token = _get_access_token()
        if not token:
            log.warning("No Firebase CLI token — Firestore updates will be skipped")

    summary = []
    for safe in args.tickers:
        safe = safe.strip().upper()
        result = backfill_ticker(safe, dry_run=args.dry_run)
        summary.append(result)

        if token and not args.skip_firestore:
            short_ticker = _ticker_base(safe)
            update_firestore_company(token, short_ticker, result, dry_run=args.dry_run)

    # Print summary
    print("\n" + "=" * 75)
    print(f"{'Ticker':<15} {'New':>6} {'Fixed':>6} {'Total':>7} {'Last Date':<12} {'Last Close':>12}")
    print("-" * 75)
    for r in summary:
        price_str = f"{r['last_price']:>12.4f}" if r.get("last_price") else "         N/A"
        print(f"{r['ticker']:<15} {r['rows_added']:>6} {r['rows_updated']:>6} "
              f"{r['total_rows']:>7} {r['last_date']:<12} {price_str}")
    print("=" * 75)
    print("New = trading days added  |  Fixed = stale rows replaced with real prices")


if __name__ == "__main__":
    main()
