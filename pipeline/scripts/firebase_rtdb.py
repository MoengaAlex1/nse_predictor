import logging
import math
import re

log = logging.getLogger(__name__)

# Display cap for change_pct_today. NSE's circuit breaker is ±9.9% but the
# scraped tiers occasionally emit >100% moves on OCR mishaps that the
# decimal-scale guard hasn't caught yet. Capping at ±15% keeps a rogue
# number from ever rendering as a giant red bar in the UI while staying
# clear of the real circuit-breaker range.
CHANGE_PCT_CAP = 15.0


def to_short_ticker(ticker: str) -> str:
    """SCOM.NR or SCOM_NR → SCOM. Splits on first dot or underscore separator."""
    return re.split(r"[._]", ticker)[0].upper()


def compute_change_pct(current: float | None, previous: float | None,
                       cap: float | None = CHANGE_PCT_CAP) -> float:
    """Canonical formula for change_pct_today. Single source of truth for
    every Firestore writer (push_intraday_prices, run_daily_update,
    run_inference). Callers must supply the last two *distinct* closes so
    the value doesn't collapse to 0 across forward-filled weekend gaps.

    Returns 0.0 when previous is missing / non-positive. Cap is applied
    symmetrically around 0 if supplied; pass cap=None for uncapped output
    (analytics / audit code). The default cap matches CHANGE_PCT_CAP so
    every writer produces the same value from the same inputs.
    """
    if current is None or previous is None or previous <= 0:
        return 0.0
    pct = (current - previous) / previous * 100.0
    if cap is not None:
        pct = max(-cap, min(cap, pct))
    return pct


def _clean(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


_FIELDS = ("o", "h", "l", "c", "v", "pc", "ch", "pch", "vv")
# Fields where 0 is a bug, not a valid value. Rendering a price=0 point on the
# chart produces the vertical drops-to-axis we've seen on SMER, KQ, EGAD etc.
# Change and volume fields are excluded — 0 is a valid "unchanged" or
# "no-trades-today" value there.
_PRICE_FIELDS = frozenset(("o", "h", "l", "c", "pc"))


def _build_node(fields: dict) -> dict:
    """
    Build a Firebase RTDB node from raw scraper fields. Price fields (o, h,
    l, c, pc) are coerced to None when they land at zero or negative — every
    zero we've traced back was either a fill-forward bug or a missing scrape,
    never an actual trade. Non-price fields keep their zeros (v=0 means "no
    trades today", ch=0 means "flat close" — both are valid data points).
    """
    out: dict = {}
    for k in _FIELDS:
        val = _clean(fields.get(k))
        if val is not None and k in _PRICE_FIELDS and val <= 0:
            # Loud on the write path so we can trace the offending caller
            # instead of silently corrupting the series.
            log.warning(
                "_build_node: dropping non-positive price %s=%s (would render "
                "as vertical spike on chart)",
                k, val,
            )
            val = None
        out[k] = val
    return out


def write_price_node(root_ref, ticker: str, date_str: str, fields: dict,
                     previous_close: float | None = None) -> None:
    """
    Write a single OHLCV node via multi-path update(). Atomically writes the
    node dict.

    When `previous_close` is supplied the row is checked for decimal-scale
    corruption first and skipped if it fails. The NSE daily band is +/-10%, so a
    close that is 10x or 100x the previous close cannot be a price move - it is
    a misread decimal point, and writing it corrupts the series. Measured on
    live data, four such rows were written in a single day (EQTY 85.25 stored as
    0.8525, CIC 4.69 as 474.00, KUKZ 425.00 as 4.28, HAFR 1.16 as 119.00).

    Callers that cannot supply a previous close keep the old behaviour.
    """
    if previous_close is not None:
        from pipeline.scripts.fix_decimal_scale import is_safe_to_write
        close = fields.get("c")
        if isinstance(close, (int, float)) and not is_safe_to_write(close, previous_close):
            log.warning(
                "REJECTED %s %s: close %s is a decimal-scale error against "
                "previous close %s - not written",
                ticker, date_str, close, previous_close,
            )
            return
    short = to_short_ticker(ticker)
    node = _build_node(fields)
    root_ref.update({f"prices/{short}/{date_str}": node})


def bulk_write_prices(root_ref, ticker: str, records: dict, batch_size: int = 500,
                      guard_decimal_scale: bool = True) -> int:
    """Write many date→fields records in batches. Returns total nodes written.

    When `guard_decimal_scale` is True (default), each row is checked against
    the CHRONOLOGICALLY-preceding row's close. A close that is a power-of-ten
    off from its predecessor is an OCR decimal shift, not a price move — the
    row is skipped and a warning is logged instead of poisoning the series.

    Uses each record's `pc` if present, otherwise falls back to the previously-
    written close in this batch. Set guard_decimal_scale=False for backfills
    that legitimately contain large gaps.

    Also maintains `prices_latest/{TICKER}` — a per-ticker mirror of the most
    recent row plus its date. The React grid views (Home, Companies, Screener,
    MarketHeatmap) fetch this mirror in one RTDB round-trip instead of doing
    a per-doc Firestore read, so a company's tile always shows the same price
    the CompanyDeepDive chart shows.
    """
    from pipeline.scripts.fix_decimal_scale import is_safe_to_write

    short = to_short_ticker(ticker)
    batch: dict = {}
    total = 0
    skipped = 0
    prev_close: float | None = None
    latest_date: str | None = None
    latest_node: dict | None = None

    for date_str in sorted(records):
        fields = records[date_str]
        close = _clean(fields.get("c"))
        anchor = _clean(fields.get("pc")) if fields.get("pc") is not None else prev_close

        if guard_decimal_scale and close is not None and anchor is not None:
            if not is_safe_to_write(close, anchor):
                log.warning(
                    "bulk_write_prices REJECTED %s %s: close %s is a decimal-"
                    "scale error vs anchor %s — not written",
                    short, date_str, close, anchor,
                )
                skipped += 1
                continue

        node = _build_node(fields)
        batch[f"prices/{short}/{date_str}"] = node
        latest_date = date_str
        latest_node = node
        if close is not None and close > 0:
            prev_close = close
        if len(batch) >= batch_size:
            root_ref.update(batch)
            total += len(batch)
            batch = {}
    if batch:
        root_ref.update(batch)
        total += len(batch)
    if skipped:
        log.warning("bulk_write_prices: skipped %d row(s) for %s (decimal-scale guard)", skipped, short)

    # Mirror the latest surviving row into prices_latest/{TICKER}. We only
    # overwrite the mirror when the batch's newest date is >= the mirror's
    # current date, so a backfill of older history can't rewind the mirror.
    if latest_date is not None and latest_node is not None:
        _maybe_update_latest_mirror(root_ref, short, latest_date, latest_node)

    return total


def _maybe_update_latest_mirror(root_ref, short: str, date_str: str, node: dict) -> None:
    """Write prices_latest/{short} when `date_str` is on-or-after the mirror's
    current `date`. Best-effort — a network error skips the mirror update
    silently rather than failing the whole batch (which already succeeded).
    """
    try:
        existing = root_ref.child(f"prices_latest/{short}/date").get()
    except Exception as e:  # noqa: BLE001 — mirror is advisory, don't fail the write
        log.warning("mirror read failed for %s: %s (skipping mirror update)", short, e)
        return
    if isinstance(existing, str) and existing > date_str:
        return
    try:
        root_ref.update({f"prices_latest/{short}": {"date": date_str, **node}})
    except Exception as e:  # noqa: BLE001
        log.warning("mirror write failed for %s %s: %s", short, date_str, e)


def bulk_delete_prices(root_ref, ticker: str, dates, batch_size: int = 500) -> int:
    """Delete many date nodes for a ticker via multi-path update(None). Returns
    the number of nodes deleted.

    Firebase RTDB semantics: setting a path to None removes the node. This is
    the only sanctioned deletion path — every cleanup script (stale-date
    scrub, quarantine push, decimal-scale scrub) MUST go through this helper
    so the write path stays a single choke point. Do NOT call
    `root_ref.update({path: None})` directly from a script.
    """
    short = to_short_ticker(ticker)
    batch: dict = {}
    total = 0
    for date_str in dates:
        batch[f"prices/{short}/{date_str}"] = None
        if len(batch) >= batch_size:
            root_ref.update(batch)
            total += len(batch)
            batch = {}
    if batch:
        root_ref.update(batch)
        total += len(batch)
    return total
