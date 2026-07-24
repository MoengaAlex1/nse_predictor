import math
import re


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


def _build_node(fields: dict) -> dict:
    return {k: _clean(fields.get(k)) for k in _FIELDS}


def write_price_node(root_ref, ticker: str, date_str: str, fields: dict) -> None:
    """Write a single OHLCV node via multi-path update(). Atomically writes the node dict."""
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
