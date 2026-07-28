"""
apply_verified_prices.py — general, ticker-agnostic daily price ingestion.

Extracts a day's OHLCV from an NSE PDF bulletin and writes each ticker's row
into data/cleaned/<TICKER>_NR_cleaned.csv, using scale_guard (see
scale_guard.py) to validate every row against that ticker's OWN trading
history before writing it.

There is nothing company-specific here — the same trend-anchored check
applies uniformly to every ticker found in the PDF, which is what this
replaces: one-off, per-company backfill scripts (e.g. apply_pdf_backfill.py)
and manual per-company data-entry commits.

Rows scale_guard resolves as "ok" or "corrected" are written (Is_Stale=0).
Rows it can't resolve are quarantined — logged with a reason and left out
of the CSV — never guessed.

Usage:
  python pipeline/scripts/apply_verified_prices.py --date 2026-07-27 --pdf 27-JUL-26.pdf
  python pipeline/scripts/apply_verified_prices.py --date 2026-07-27 --pdf 27-JUL-26.pdf --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.scripts.scrape_nse_pdf import build_pdf_url, download_pdf, extract_price_rows  # noqa: E402
from pipeline.scripts.scale_guard import check_scale, median_reference  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

DATA_CLEANED = REPO_ROOT / "data" / "cleaned"

# Real trading days used to build each ticker's historical reference price.
RECENT_WINDOW = 5


def _csv_path(ticker: str) -> Path:
    return DATA_CLEANED / f"{ticker}_NR_cleaned.csv"


def load_history(ticker: str) -> pd.DataFrame | None:
    path = _csv_path(ticker)
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["Date"])
    return df


def recent_closes(history: pd.DataFrame | None, before_date: datetime.date) -> list[float]:
    """The last RECENT_WINDOW real (Is_Stale=0, Volume>0) closes strictly
    before before_date — raw values, not yet reduced to a single reference,
    so callers can pool them with other independent evidence (e.g. the next
    day's PDF) before taking one robust median."""
    if history is None or history.empty:
        return []
    solid = history[
        (history["Is_Stale"] == 0)
        & (history["Volume"] > 0)
        & (history["Date"].dt.date < before_date)
    ]
    if solid.empty:
        return []
    return solid.sort_values("Date")["Close"].tail(RECENT_WINDOW).tolist()


def next_day_prev_close(ticker: str, next_day_fields: dict[str, dict] | None) -> float | None:
    """The next trading day's PDF independently re-reports 'previous close' —
    a second, independently-OCR'd read of today's true close. Used as one
    more vote in the trend reference, which is what catches scale errors on
    thinly-traded/newly-listed tickers where CSV history is too short to
    trust on its own."""
    if not next_day_fields:
        return None
    fields = next_day_fields.get(ticker)
    if not fields:
        return None
    prev = fields.get("prev_close")
    return prev if prev and prev > 0 else None


def write_row(ticker: str, history: pd.DataFrame | None, target_date: datetime.date, row: dict) -> None:
    new_row = pd.DataFrame([{
        "Date": pd.Timestamp(target_date),
        "Open": row["open"],
        "High": row["high"],
        "Low": row["low"],
        "Close": row["close"],
        "Volume": row["volume"],
        "Is_Stale": 0,
        "Ticker": ticker,
    }])
    if history is None or history.empty:
        combined = new_row
    else:
        combined = pd.concat(
            [history[history["Date"].dt.date != target_date], new_row],
            ignore_index=True,
        )
    combined = combined.sort_values("Date")
    combined.to_csv(_csv_path(ticker), index=False)


def apply_prices(
    target_date: datetime.date,
    pdf_bytes: bytes,
    dry_run: bool = False,
    resolution: int = 250,
    next_day_pdf_bytes: bytes | None = None,
) -> dict[str, Any]:
    rows = extract_price_rows(pdf_bytes, resolution=resolution)

    next_day_fields: dict[str, dict] | None = None
    if next_day_pdf_bytes is not None:
        next_day_fields = dict(extract_price_rows(next_day_pdf_bytes, resolution=resolution))

    written: list[str] = []
    corrected: list[dict] = []
    quarantined: list[dict] = []
    no_history: list[str] = []

    for ticker, fields in rows:
        history = load_history(ticker)
        candidates = recent_closes(history, target_date)
        corroboration = next_day_prev_close(ticker, next_day_fields)
        if corroboration is not None:
            candidates = [*candidates, corroboration]
        reference = median_reference(candidates)
        if reference is None:
            no_history.append(ticker)

        result = check_scale(
            open_=fields["open"], high=fields["high"], low=fields["low"], close=fields["close"],
            reference_close=reference,
        )

        if result.status == "quarantine":
            quarantined.append({"ticker": ticker, "reason": result.reason, "fields": fields})
            log.warning("QUARANTINED %s: %s", ticker, result.reason)
            continue

        if result.status == "corrected":
            corrected.append({
                "ticker": ticker,
                "factor": result.factor,
                "old_close": fields["close"],
                "new_close": result.close,
            })
            log.info(
                "CORRECTED %s: %.4f -> %.4f (factor %.4g, reference %.4f)",
                ticker, fields["close"], result.close, result.factor, reference,
            )

        row = {
            "open": result.open, "high": result.high, "low": result.low, "close": result.close,
            "volume": fields.get("volume", 0),
        }
        if not dry_run:
            write_row(ticker, history, target_date, row)
        written.append(ticker)

    log.info(
        "=== %s: %d written (%d corrected), %d quarantined, %d with no history ===",
        target_date.isoformat(), len(written), len(corrected), len(quarantined), len(no_history),
    )

    return {
        "date": target_date.isoformat(),
        "written": written,
        "corrected": corrected,
        "quarantined": quarantined,
        "no_history": no_history,
    }


def _next_trading_day(d: datetime.date) -> datetime.date:
    nxt = d + datetime.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += datetime.timedelta(days=1)
    return nxt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a day's verified NSE prices to data/cleaned CSVs (any ticker, no hardcoding)",
    )
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--pdf", help="Local PDF path (skip download)")
    parser.add_argument(
        "--next-pdf",
        help="Local PDF path for the following trading day, used to cross-check "
             "prev_close (skip auto-download)",
    )
    parser.add_argument(
        "--no-next-day-check",
        action="store_true",
        help="Don't fetch/use the next trading day's PDF for corroboration",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing")
    parser.add_argument("--resolution", type=int, default=250)
    args = parser.parse_args()

    target_date = datetime.date.fromisoformat(args.date)

    if args.pdf:
        pdf_bytes = Path(args.pdf).read_bytes()
    else:
        pdf_bytes = download_pdf(build_pdf_url(target_date))

    next_day_pdf_bytes = None
    if args.next_pdf:
        next_day_pdf_bytes = Path(args.next_pdf).read_bytes()
    elif not args.no_next_day_check:
        next_date = _next_trading_day(target_date)
        try:
            next_day_pdf_bytes = download_pdf(build_pdf_url(next_date))
            log.info("Using %s bulletin to cross-check prev_close", next_date.isoformat())
        except Exception as exc:
            log.warning("Next-day PDF (%s) unavailable — proceeding without it: %s", next_date, exc)

    apply_prices(
        target_date, pdf_bytes, dry_run=args.dry_run, resolution=args.resolution,
        next_day_pdf_bytes=next_day_pdf_bytes,
    )


if __name__ == "__main__":
    main()
