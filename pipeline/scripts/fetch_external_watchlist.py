"""Fetch quotes for the workstation's non-NSE watchlist symbols.

Originally routed via Stooq's CSV endpoint but Stooq gated that behind
a JS browser-verification challenge in mid-2026, so we pivoted to
`yfinance` (already a project dep — see pipeline/requirements.txt).
yfinance is a free, unauthenticated wrapper around Yahoo Finance
quotes; works reliably for US indices, US stocks, and continuous
futures — everything the TradingWorkstation's right sidebar lists.

Writes to RTDB `watchlist/external/{SYMBOL}` = {
  "last": float, "chg": float, "chg_pct": float,
  "open": float | None,
  "date": "YYYY-MM-DD",
  "updated_at": ISO-8601 UTC,
  "yf_symbol": "AAPL",
  "source": "yfinance",
}

Failure semantics: per-symbol errors are logged and swallowed so one
bad symbol never blocks the others. The whole run only exits non-zero
if RTDB init fails.

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \\
    python pipeline/scripts/fetch_external_watchlist.py
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


# Display symbol → Yahoo Finance symbol. Yahoo's convention:
#   Indices are prefixed with ^ (^GSPC, ^IXIC, ^DJI, ^VIX)
#   Continuous futures use =F suffix (CL=F, GC=F)
#   US stocks are plain (AAPL)
#   DXY (US Dollar Index) is DX-Y.NYB
# Confirmed against a manual yfinance call on 2026-09-21.
SYMBOLS: list[tuple[str, str]] = [
    # Indices
    ("SPX",   "^GSPC"),      # S&P 500
    ("NDQ",   "^IXIC"),      # Nasdaq Composite
    ("DJI",   "^DJI"),       # Dow Jones Industrial Average
    ("VIX",   "^VIX"),       # CBOE Volatility Index
    ("DXY",   "DX-Y.NYB"),   # ICE US Dollar Index
    # Stocks
    ("AAPL",  "AAPL"),
    ("TSLA",  "TSLA"),
    ("NFLX",  "NFLX"),
    # Futures
    ("USOIL", "CL=F"),       # WTI Crude continuous
    ("GOLD",  "GC=F"),       # Gold continuous
]


def _fetch_quote(yf_symbol: str) -> dict | None:
    """Return {last, chg, chg_pct, open, date} or None on failure.

    Uses yfinance's Ticker.fast_info + a 2-day history fallback so we
    always have a `chg` computed from the actual previous close, not
    from the same-session open (which underestimates the daily move).
    """
    try:
        import yfinance as yf
    except ImportError:
        log.error("yfinance not installed — add to pipeline/requirements.txt")
        return None

    try:
        t = yf.Ticker(yf_symbol)
        # fast_info is Yahoo's lightweight snapshot; last_price is the
        # most recent trade, previous_close is yesterday's official close.
        info = t.fast_info
        last = float(info.get("last_price") or info.get("regular_market_price") or 0.0) or None
        prev = float(info.get("previous_close") or info.get("regular_market_previous_close") or 0.0) or None
        open_ = float(info.get("open") or info.get("regular_market_open") or 0.0) or None
    except Exception as e:  # noqa: BLE001 — fast_info can throw on odd symbols
        log.warning("yfinance fast_info failed for %s (%s) — falling back to history",
                    yf_symbol, e)
        last = prev = open_ = None

    # Fallback: pull the last 5 daily bars and take last two closes.
    if last is None or prev is None:
        try:
            import yfinance as yf
            hist = yf.Ticker(yf_symbol).history(period="5d", auto_adjust=False)
            if hist is not None and len(hist) >= 2:
                last = float(hist["Close"].iloc[-1])
                prev = float(hist["Close"].iloc[-2])
                open_ = float(hist["Open"].iloc[-1]) if "Open" in hist.columns else None
        except Exception as e:  # noqa: BLE001
            log.warning("yfinance history fallback failed for %s: %s", yf_symbol, e)

    if last is None or prev is None:
        return None

    chg = round(last - prev, 4)
    chg_pct = round(chg / prev * 100, 4) if prev > 0 else None
    return {
        "last":     round(last, 4),
        "chg":      chg,
        "chg_pct":  chg_pct,
        "open":     round(open_, 4) if open_ is not None else None,
        "date":     datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


def main() -> None:
    from pipeline.scripts.firebase_client import get_rtdb
    root = get_rtdb()

    now_utc = datetime.now(timezone.utc).isoformat()
    written = 0
    failed: list[str] = []

    for display, yf_symbol in SYMBOLS:
        quote = _fetch_quote(yf_symbol)
        if quote is None:
            failed.append(display)
            continue
        node = {
            **quote,
            "yf_symbol":  yf_symbol,
            "source":     "yfinance",
            "updated_at": now_utc,
        }
        try:
            root.update({f"watchlist/external/{display}": node})
            written += 1
            log.info(
                "%-6s (%s)  last=%s  chg=%s  chg%%=%s  as-of=%s",
                display, yf_symbol,
                node["last"], node["chg"], node["chg_pct"], node["date"],
            )
        except Exception as e:  # noqa: BLE001
            log.warning("RTDB write failed for %s: %s", display, e)
            failed.append(display)

    log.info("Done — %d/%d symbols written", written, len(SYMBOLS))
    if failed:
        log.warning("Failed: %s", ", ".join(failed))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
