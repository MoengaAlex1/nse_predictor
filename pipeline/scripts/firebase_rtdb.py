import logging
import math
import re

log = logging.getLogger(__name__)


def to_short_ticker(ticker: str) -> str:
    """SCOM.NR or SCOM_NR → SCOM. Splits on first dot or underscore separator."""
    return re.split(r"[._]", ticker)[0].upper()


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


def bulk_write_prices(root_ref, ticker: str, records: dict, batch_size: int = 500) -> int:
    """Write many date→fields records in batches. Returns total nodes written."""
    short = to_short_ticker(ticker)
    batch: dict = {}
    total = 0
    for date_str, fields in records.items():
        node = _build_node(fields)
        batch[f"prices/{short}/{date_str}"] = node
        if len(batch) >= batch_size:
            root_ref.update(batch)
            total += len(batch)
            batch = {}
    if batch:
        root_ref.update(batch)
        total += len(batch)
    return total
