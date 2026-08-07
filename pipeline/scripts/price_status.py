"""
price_status.py

Single source of truth for how a company's price for a given trading day is
labelled, shared by the two writers that can touch it:

  push_intraday_prices.py  → PROVISIONAL  (live scrape, 5x during the session)
  scrape_nse_pdf.py        → FINAL        (official NSE daily report PDF)

The NSE only publishes the daily report PDF *after* the market closes (~15:30
EAT), so for most of the trading day the only price available is the live
last-traded figure. That number is genuinely useful — it just is not settled.
Labelling it lets the frontend show today's movement while making clear the
figure can still change, and show a settled state once the PDF lands.

Status is stored on the Firestore `companies/{short}` document, which is what
the web app reads. The RTDB OHLCV nodes written by the PDF scraper are left
alone: their schema is a fixed numeric field whitelist (see firebase_rtdb.
_FIELDS) and every value is coerced through float(), so a string marker
cannot live there.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# NSE trades in East Africa Time (UTC+3, no DST).
EAT = timezone(timedelta(hours=3))

PROVISIONAL = "provisional"
FINAL = "final"

SOURCE_LIVE = "live"
SOURCE_NSE_PDF = "nse_pdf"


def today_eat() -> str:
    """Current trading date in EAT as YYYY-MM-DD."""
    return datetime.now(EAT).strftime("%Y-%m-%d")


def now_eat_iso() -> str:
    """Current EAT timestamp, ISO-8601 with offset — for `price_finalized_at`."""
    return datetime.now(EAT).isoformat(timespec="seconds")


def provisional_fields(trading_date: str, *, as_of: str | None = None) -> dict:
    """
    Firestore fields marking `trading_date`'s price as live-but-unsettled.

    `as_of` is the HH:MM EAT the snapshot was taken, so the UI can say
    "as of 13:00" rather than just "provisional".
    """
    fields = {
        "price_status": PROVISIONAL,
        "price_status_date": trading_date,
        "price_source": SOURCE_LIVE,
    }
    if as_of:
        fields["price_as_of"] = as_of
    return fields


def final_fields(trading_date: str) -> dict:
    """Firestore fields marking `trading_date`'s price as settled from the PDF."""
    return {
        "price_status": FINAL,
        "price_status_date": trading_date,
        "price_source": SOURCE_NSE_PDF,
        "price_finalized_at": now_eat_iso(),
    }


def is_already_final(existing: dict | None, trading_date: str) -> bool:
    """
    True when `existing` (a Firestore company doc) already records a FINAL
    price for `trading_date`.

    Guards against a live scrape that lands after the PDF has settled the day
    — which would otherwise flip a settled price back to provisional. Status
    from any *other* date is irrelevant: a new trading day always starts
    provisional.
    """
    if not existing:
        return False
    return (
        existing.get("price_status") == FINAL
        and existing.get("price_status_date") == trading_date
    )
