"""
Price Audit Agent — cross-checks RTDB prices against NSE Kenya live data.

NSE publishes live prices via a WordPress AJAX endpoint. This script:
  1. Fetches today's (or latest) prices from NSE's AJAX endpoint
  2. Reads the corresponding RTDB records for the same date
  3. Flags discrepancies > TOLERANCE% between NSE live price and RTDB close
  4. Applies the same consecutive-ratio spike detection as fix_all_decimals.py
  5. Patches any bad RTDB records directly

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \\
    python pipeline/scripts/audit_prices_vs_nse.py [--dry-run] [--date YYYY-MM-DD]
"""
import argparse
import datetime
import json
import logging
import sys
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

NSE_AJAX_URL = "https://www.nse.co.ke/wp-admin/admin-ajax.php"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NSEAudit/1.0)",
    "Referer": "https://www.nse.co.ke/market-statistics/",
}
# Accept a discrepancy of up to 1% between NSE website price and RTDB price
TOLERANCE = 0.01
# Minimum spike ratio for consecutive-day decimal detection
JUMP_RATIO = 10.0
RESTORE_LO = 0.5
RESTORE_HI = 2.0


def fetch_nse_prices() -> dict[str, float]:
    """
    Fetch latest prices from NSE AJAX endpoint.
    Returns {ticker_code: close_price}.
    """
    payload = {
        "action": "get_listed_companies_data",
        "security": "",
    }
    try:
        resp = requests.post(NSE_AJAX_URL, data=payload, headers=NSE_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        prices: dict[str, float] = {}
        rows = data if isinstance(data, list) else data.get("data", [])
        for row in rows:
            code = (row.get("symbol") or row.get("code") or "").strip().upper()
            price_raw = row.get("close") or row.get("price") or row.get("last_price")
            if code and price_raw:
                try:
                    prices[code] = float(str(price_raw).replace(",", ""))
                except (ValueError, TypeError):
                    pass
        log.info("Fetched %d prices from NSE website", len(prices))
        return prices
    except Exception as exc:
        log.warning("NSE AJAX fetch failed: %s — skipping cross-check", exc)
        return {}


def fetch_rtdb_prices(root_ref, ticker: str, date_str: str) -> dict | None:
    """Read a single date record from RTDB."""
    try:
        short = ticker.split("_")[0].upper()
        snap = root_ref.child(f"prices/{short}/{date_str}").get()
        return dict(snap) if snap else None
    except Exception as exc:
        log.warning("RTDB read %s/%s failed: %s", ticker, date_str, exc)
        return None


def fetch_all_ticker_prices(root_ref, short: str) -> dict[str, dict]:
    """Read all date records for a ticker from RTDB."""
    try:
        snap = root_ref.child(f"prices/{short}").get()
        return dict(snap) if snap else {}
    except Exception as exc:
        log.warning("RTDB read prices/%s failed: %s", short, exc)
        return {}


def detect_spikes(records: dict[str, dict]) -> list[tuple[str, str, float, float]]:
    """
    Consecutive-ratio spike detection on RTDB close prices.
    Returns list of (date_str, field, bad_value, fixed_value).
    """
    sorted_dates = sorted(records.keys())
    fixes = []

    for field in ("o", "h", "l", "c"):
        vals: list[tuple[str, float | None]] = [
            (d, records[d].get(field)) for d in sorted_dates
        ]
        positive = [(d, v) for d, v in vals if v and v > 0]
        n = len(positive)

        for i, (date_str, val) in enumerate(positive):
            prev = positive[i - 1][1] if i > 0 else None
            nxt  = positive[i + 1][1] if i < n - 1 else None

            is_spike = False
            ref = None
            if prev and nxt:
                if (val / prev >= JUMP_RATIO) and (val / nxt >= JUMP_RATIO):
                    is_spike = True
                    ref = (prev + nxt) / 2
            elif prev and not nxt:
                if val / prev >= JUMP_RATIO:
                    is_spike = True
                    ref = prev
            elif nxt and not prev:
                if val / nxt >= JUMP_RATIO:
                    is_spike = True
                    ref = nxt

            if is_spike and ref and ref > 0:
                for divisor in (10, 100):
                    candidate = round(val / divisor, 4)
                    if RESTORE_LO * ref <= candidate <= RESTORE_HI * ref:
                        fixes.append((date_str, field, val, candidate))
                        break

    return fixes


def patch_rtdb(root_ref, short: str, date_str: str, field: str, value: float, dry_run: bool) -> None:
    if dry_run:
        return
    try:
        root_ref.child(f"prices/{short}/{date_str}").update({field: value})
    except Exception as exc:
        log.error("RTDB patch %s/%s/%s failed: %s", short, date_str, field, exc)


def audit_ticker(root_ref, short: str, nse_prices: dict[str, float], target_date: str | None, dry_run: bool) -> int:
    """Audit a single ticker. Returns count of fixes applied."""
    records = fetch_all_ticker_prices(root_ref, short)
    if not records:
        log.debug("  %s: no RTDB data", short)
        return 0

    fixes_applied = 0

    # 1. NSE website cross-check for the target date
    if target_date and target_date in records:
        nse_price = nse_prices.get(short)
        rtdb_close = records[target_date].get("c")
        if nse_price and rtdb_close and nse_price > 0 and rtdb_close > 0:
            diff = abs(nse_price - rtdb_close) / nse_price
            if diff > TOLERANCE:
                log.warning(
                    "  %s %s: NSE=%.4f RTDB=%.4f (%.1f%% diff) — likely decimal error",
                    short, target_date, nse_price, rtdb_close, diff * 100,
                )
                # If RTDB is ~10x or ~100x NSE, fix it
                for divisor in (10, 100):
                    if abs(rtdb_close / divisor - nse_price) / nse_price <= TOLERANCE:
                        fixed = round(rtdb_close / divisor, 4)
                        log.info("  %s %s: patching c %.4f → %.4f", short, target_date, rtdb_close, fixed)
                        patch_rtdb(root_ref, short, target_date, "c", fixed, dry_run)
                        fixes_applied += 1
                        break

    # 2. Consecutive-ratio spike detection across all history
    spikes = detect_spikes(records)
    for date_str, field, bad_val, fixed_val in spikes:
        log.info("  %s %s %s: spike %.4f → %.4f", short, date_str, field, bad_val, fixed_val)
        patch_rtdb(root_ref, short, date_str, field, fixed_val, dry_run)
        fixes_applied += 1

    return fixes_applied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--date", help="Date to cross-check with NSE website (YYYY-MM-DD, default: today)")
    parser.add_argument("--ticker", help="Audit single ticker only")
    args = parser.parse_args()

    target_date = args.date or datetime.date.today().strftime("%Y-%m-%d")

    from pipeline.scripts.firebase_client import get_rtdb
    root_ref = get_rtdb()

    # Fetch live NSE prices for cross-check
    nse_prices = fetch_nse_prices()

    # Discover all tickers from RTDB
    if args.ticker:
        tickers = [args.ticker.upper()]
    else:
        try:
            snap = root_ref.child("prices").get()
            tickers = list(snap.keys()) if snap else []
        except Exception as exc:
            log.error("Failed to list RTDB tickers: %s", exc)
            sys.exit(1)

    log.info("Auditing %d tickers for %s (dry_run=%s)", len(tickers), target_date, args.dry_run)

    total_fixes = 0
    for short in sorted(tickers):
        try:
            total_fixes += audit_ticker(root_ref, short, nse_prices, target_date, args.dry_run)
        except Exception as exc:
            log.error("  %s: audit failed — %s", short, exc)

    log.info("=" * 60)
    log.info("Audit complete — %d fixes applied (dry_run=%s)", total_fixes, args.dry_run)


if __name__ == "__main__":
    main()
