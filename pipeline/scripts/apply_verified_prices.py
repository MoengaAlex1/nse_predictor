"""
apply_verified_prices.py — general, ticker-agnostic daily price ingestion.

Every known company must end up with a row for target_date — either a real
verified trade or an explicit "no trade" flat row — never a silent gap.
Resolution escalates through independent sources, trusting the first one
scale_guard (see scale_guard.py) confirms is both trend-consistent and
internally OHLC-valid:

  1. Primary OCR pass on the day's PDF bulletin.
  2. Re-OCR the SAME pdf at a higher resolution. OCR is the most
     error-prone step in this pipeline (dropped digits, decimal-shift
     misreads); a second pass at a different DPI often reads cleanly what
     the first pass mangled.
  3. An independent accredited source (afx.kwayisi.org) for the same date —
     a genuinely different extraction pipeline, so it can't repeat the same
     OCR mistake as steps 1-2.
  4. Forward-fill the last real close as a flat no-trade row (Is_Stale=1,
     Volume=0). This is the definition of "no trade that day," not a
     guess, and is the only step guaranteed to succeed — it's what
     guarantees every company has a daily price.

There is nothing company-specific in any of this — the same escalation
chain applies uniformly to every ticker with a CSV in data/cleaned/,
replacing one-off per-company backfill scripts and manual data-entry
commits.

Usage:
  python pipeline/scripts/apply_verified_prices.py --date 2026-07-27 --pdf 27-JUL-26.pdf
  python pipeline/scripts/apply_verified_prices.py --date 2026-07-27 --pdf 27-JUL-26.pdf --dry-run

  # Audit/backfill a date range (any ticker subset via --only-tickers, or all):
  python pipeline/scripts/apply_verified_prices.py --start-date 2025-10-30 --end-date 2026-07-28 --only-tickers CGEN
"""
from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import requests

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

# Second OCR pass DPI, tried only for tickers missing/quarantined at the
# default (250) resolution used for the primary pass.
RETRY_RESOLUTION = 300


def _csv_path(ticker: str) -> Path:
    return DATA_CLEANED / f"{ticker}_NR_cleaned.csv"


def all_known_tickers() -> list[str]:
    return sorted(p.stem.replace("_NR_cleaned", "") for p in DATA_CLEANED.glob("*_NR_cleaned.csv"))


def load_history(ticker: str) -> pd.DataFrame | None:
    path = _csv_path(ticker)
    if not path.exists():
        return None
    return pd.read_csv(path, parse_dates=["Date"])


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


def fetch_alt_source_row(ticker: str, target_date: datetime.date) -> dict | None:
    """Independent accredited source (afx.kwayisi.org) for target_date — a
    completely different extraction pipeline from the PDF/OCR path, so it
    can't repeat the same OCR mistake. Only covers the last ~10 trading
    days, so it's only useful as a fallback for recent dates."""
    from pipeline.scripts.backfill_prices import fetch_afx_history

    try:
        df = fetch_afx_history(f"{ticker}_NR")
    except Exception as exc:
        log.debug("alt source fetch failed for %s: %s", ticker, exc)
        return None
    if df is None or df.empty:
        return None
    ts = pd.Timestamp(target_date)
    if ts not in df.index:
        return None
    row = df.loc[ts]
    close = float(row["Close"])
    return {
        "open": close, "high": close, "low": close, "close": close,
        "volume": float(row.get("Volume", 0) or 0),
    }


def forward_fill_row(history: pd.DataFrame | None, target_date: datetime.date) -> dict | None:
    """Last real close repeated flat — the correct representation of 'this
    company did not trade today,' not a guess. Only reached once no source
    (OCR, retry, alt) produced a usable row."""
    if history is None or history.empty:
        return None
    solid = history[(history["Is_Stale"] == 0) & (history["Date"].dt.date < target_date)]
    if solid.empty:
        return None
    last_close = float(solid.sort_values("Date").iloc[-1]["Close"])
    return {"open": last_close, "high": last_close, "low": last_close, "close": last_close, "volume": 0.0}


def write_row(
    ticker: str,
    history: pd.DataFrame | None,
    target_date: datetime.date,
    row: dict,
    is_stale: int = 0,
) -> None:
    new_row = pd.DataFrame([{
        "Date": pd.Timestamp(target_date),
        "Open": row["open"],
        "High": row["high"],
        "Low": row["low"],
        "Close": row["close"],
        "Volume": row["volume"],
        "Is_Stale": is_stale,
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


def resolve_ticker(
    ticker: str,
    target_date: datetime.date,
    attempts: list[tuple[str, dict | None]],
    history: pd.DataFrame | None,
    next_day_fields: dict[str, dict] | None,
) -> dict[str, Any]:
    """Try each (source_name, fields) pair in order; use the first one
    scale_guard confirms. Falls back to forward-fill if none resolve."""
    candidates = recent_closes(history, target_date)
    corroboration = next_day_prev_close(ticker, next_day_fields)
    if corroboration is not None:
        candidates = [*candidates, corroboration]
    reference = median_reference(candidates)

    for source, fields in attempts:
        if not fields:
            continue
        result = check_scale(
            open_=fields["open"], high=fields["high"], low=fields["low"], close=fields["close"],
            reference_close=reference,
        )
        if result.status in ("ok", "corrected"):
            return {
                "status": result.status, "source": source, "reference": reference,
                "row": {"open": result.open, "high": result.high, "low": result.low, "close": result.close,
                        "volume": fields.get("volume", 0)},
                "factor": result.factor, "raw_close": fields["close"], "is_stale": 0,
            }

    alt = fetch_alt_source_row(ticker, target_date)
    if alt:
        result = check_scale(
            open_=alt["open"], high=alt["high"], low=alt["low"], close=alt["close"],
            reference_close=reference,
        )
        if result.status in ("ok", "corrected"):
            return {
                "status": result.status, "source": "alt_source", "reference": reference,
                "row": {"open": result.open, "high": result.high, "low": result.low, "close": result.close,
                        "volume": alt.get("volume", 0)},
                "factor": result.factor, "raw_close": alt["close"], "is_stale": 0,
            }

    filled = forward_fill_row(history, target_date)
    if filled:
        return {"status": "forward_filled", "source": "forward_fill", "reference": reference,
                "row": filled, "factor": 1.0, "raw_close": filled["close"], "is_stale": 1}

    return {"status": "unresolved", "source": None, "reference": reference, "row": None}


def apply_prices(
    target_date: datetime.date,
    pdf_bytes: bytes,
    dry_run: bool = False,
    resolution: int = 250,
    next_day_pdf_bytes: bytes | None = None,
    only_tickers: list[str] | None = None,
) -> dict[str, Any]:
    primary = dict(extract_price_rows(pdf_bytes, resolution=resolution))

    next_day_fields: dict[str, dict] | None = None
    if next_day_pdf_bytes is not None:
        next_day_fields = dict(extract_price_rows(next_day_pdf_bytes, resolution=resolution))

    tickers = sorted(set(all_known_tickers()) | set(primary))
    if only_tickers is not None:
        tickers = [t for t in tickers if t in set(only_tickers)]

    # Only pay for a second full-page OCR pass if something actually needs it.
    needs_retry = False
    for ticker in tickers:
        fields = primary.get(ticker)
        if not fields:
            needs_retry = True
            break
        history = load_history(ticker)
        candidates = recent_closes(history, target_date)
        reference = median_reference(candidates)
        if check_scale(fields["open"], fields["high"], fields["low"], fields["close"], reference).status == "quarantine":
            needs_retry = True
            break

    retry: dict[str, dict] = {}
    if needs_retry:
        log.info("Re-OCR at %d dpi for tickers unresolved at the primary pass …", RETRY_RESOLUTION)
        retry = dict(extract_price_rows(pdf_bytes, resolution=RETRY_RESOLUTION))

    written: list[str] = []
    corrected: list[dict] = []
    forward_filled: list[str] = []
    unresolved: list[dict] = []

    for ticker in tickers:
        history = load_history(ticker)
        attempts = [("ocr_primary", primary.get(ticker)), ("ocr_retry", retry.get(ticker))]
        outcome = resolve_ticker(ticker, target_date, attempts, history, next_day_fields)

        if outcome["status"] == "unresolved":
            unresolved.append({"ticker": ticker, "reason": "no source resolved and no history to forward-fill"})
            log.warning("UNRESOLVED %s: no source usable and no history to forward-fill from", ticker)
            continue

        if outcome["source"] != "ocr_primary" or outcome["status"] == "corrected":
            log.info(
                "%s %s: source=%s close %.4f -> %.4f",
                outcome["status"].upper(), ticker, outcome["source"],
                outcome["raw_close"], outcome["row"]["close"],
            )

        if outcome["status"] == "corrected":
            corrected.append({
                "ticker": ticker, "source": outcome["source"], "factor": outcome["factor"],
                "old_close": outcome["raw_close"], "new_close": outcome["row"]["close"],
            })
        if outcome["status"] == "forward_filled":
            forward_filled.append(ticker)

        if not dry_run:
            write_row(ticker, history, target_date, outcome["row"], is_stale=outcome["is_stale"])
        written.append(ticker)

    log.info(
        "=== %s: %d/%d companies covered (%d corrected, %d forward-filled), %d unresolved ===",
        target_date.isoformat(), len(written), len(tickers), len(corrected), len(forward_filled),
        len(unresolved),
    )

    return {
        "date": target_date.isoformat(),
        "written": written,
        "corrected": corrected,
        "forward_filled": forward_filled,
        "unresolved": unresolved,
    }


def _next_trading_day(d: datetime.date) -> datetime.date:
    nxt = d + datetime.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += datetime.timedelta(days=1)
    return nxt


def trading_days(start: datetime.date, end: datetime.date) -> list[datetime.date]:
    days = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += datetime.timedelta(days=1)
    return days


def apply_date_range(
    start: datetime.date,
    end: datetime.date,
    only_tickers: list[str] | None = None,
    dry_run: bool = False,
    resolution: int = 250,
) -> list[dict[str, Any]]:
    """Reprocess every trading day in [start, end] through the same
    escalation chain as a single-day run. Each day's PDF is downloaded once
    and reused as the next-day corroboration source for the day before it,
    so a 194-day audit still only fetches 194 PDFs, not 388."""
    days = trading_days(start, end)
    pdf_cache: dict[datetime.date, bytes | None] = {}

    def get_pdf(d: datetime.date) -> bytes | None:
        if d not in pdf_cache:
            try:
                pdf_cache[d] = download_pdf(build_pdf_url(d))
            except Exception as exc:
                log.warning("No PDF for %s (holiday/404?) — skipping: %s", d, exc)
                pdf_cache[d] = None
        return pdf_cache[d]

    reports: list[dict[str, Any]] = []
    for i, d in enumerate(days):
        pdf_bytes = get_pdf(d)
        if pdf_bytes is None:
            continue
        next_pdf = get_pdf(days[i + 1]) if i + 1 < len(days) else None
        report = apply_prices(
            d, pdf_bytes, dry_run=dry_run, resolution=resolution,
            next_day_pdf_bytes=next_pdf, only_tickers=only_tickers,
        )
        reports.append(report)
        if i > 0:
            pdf_cache.pop(days[i - 1], None)  # bound memory to ~2 PDFs at a time

    total_corrected = sum(len(r["corrected"]) for r in reports)
    total_forward_filled = sum(len(r["forward_filled"]) for r in reports)
    total_unresolved = sum(len(r["unresolved"]) for r in reports)
    log.info(
        "=== range %s to %s: %d days processed, %d corrected, %d forward-filled, %d unresolved ===",
        start.isoformat(), end.isoformat(), len(reports),
        total_corrected, total_forward_filled, total_unresolved,
    )
    return reports


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply a day's verified NSE prices to data/cleaned CSVs (any ticker, no hardcoding)",
    )
    parser.add_argument("--date", help="YYYY-MM-DD (single-day mode)")
    parser.add_argument("--start-date", help="YYYY-MM-DD (range mode, use with --end-date)")
    parser.add_argument("--end-date", help="YYYY-MM-DD (range mode, use with --start-date)")
    parser.add_argument("--pdf", help="Local PDF path (skip download, single-day mode only)")
    parser.add_argument(
        "--next-pdf",
        help="Local PDF path for the following trading day, used to cross-check "
             "prev_close (skip auto-download, single-day mode only)",
    )
    parser.add_argument(
        "--no-next-day-check",
        action="store_true",
        help="Don't fetch/use the next trading day's PDF for corroboration",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing")
    parser.add_argument("--resolution", type=int, default=250)
    parser.add_argument(
        "--only-tickers", nargs="+",
        help="Restrict writes to these tickers only (e.g. --only-tickers CGEN). "
             "The PDF is still fully OCR'd either way; this just scopes what gets written.",
    )
    args = parser.parse_args()

    if args.start_date or args.end_date:
        if not (args.start_date and args.end_date):
            parser.error("--start-date and --end-date must be used together")
        apply_date_range(
            datetime.date.fromisoformat(args.start_date),
            datetime.date.fromisoformat(args.end_date),
            only_tickers=args.only_tickers, dry_run=args.dry_run, resolution=args.resolution,
        )
        return

    if not args.date:
        parser.error("--date is required in single-day mode (or use --start-date/--end-date)")

    target_date = datetime.date.fromisoformat(args.date)

    if args.pdf:
        pdf_bytes = Path(args.pdf).read_bytes()
    else:
        try:
            pdf_bytes = download_pdf(build_pdf_url(target_date))
        except requests.HTTPError as exc:
            # NSE publishes the daily PDF ~15:30-16:00 EAT. Earlier scheduled
            # slots (or a late-publishing day) will 404 — exit 0 so the
            # workflow reports success and later slots retry, rather than
            # spamming the failed-runs list.
            log.warning("PDF for %s not available yet: %s — skipping this run", target_date, exc)
            return

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
        next_day_pdf_bytes=next_day_pdf_bytes, only_tickers=args.only_tickers,
    )


if __name__ == "__main__":
    main()
