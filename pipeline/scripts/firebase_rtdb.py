import math


def to_short_ticker(ticker: str) -> str:
    """SCOM.NR or SCOM_NR → SCOM."""
    return ticker.replace(".NR", "").replace("_NR", "").replace(".", "").upper()


def _clean(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def write_price_node(root_ref, ticker: str, date_str: str, fields: dict) -> None:
    """Write a single OHLCV node. Uses update() so existing nodes are never overwritten."""
    short = to_short_ticker(ticker)
    node = {
        "o":   _clean(fields.get("o")),
        "h":   _clean(fields.get("h")),
        "l":   _clean(fields.get("l")),
        "c":   _clean(fields.get("c")),
        "v":   _clean(fields.get("v")),
        "pc":  _clean(fields.get("pc")),
        "ch":  _clean(fields.get("ch")),
        "pch": _clean(fields.get("pch")),
        "vv":  _clean(fields.get("vv")),
    }
    root_ref.update({f"prices/{short}/{date_str}": node})


def bulk_write_prices(root_ref, ticker: str, records: dict, batch_size: int = 500) -> int:
    """Write many date→fields records in batches. Returns total nodes written."""
    short = to_short_ticker(ticker)
    batch: dict = {}
    total = 0
    for date_str, fields in records.items():
        node = {
            "o":   _clean(fields.get("o")),
            "h":   _clean(fields.get("h")),
            "l":   _clean(fields.get("l")),
            "c":   _clean(fields.get("c")),
            "v":   _clean(fields.get("v")),
            "pc":  _clean(fields.get("pc")),
            "ch":  _clean(fields.get("ch")),
            "pch": _clean(fields.get("pch")),
            "vv":  _clean(fields.get("vv")),
        }
        batch[f"prices/{short}/{date_str}"] = node
        if len(batch) >= batch_size:
            root_ref.update(batch)
            total += len(batch)
            batch = {}
    if batch:
        root_ref.update(batch)
        total += len(batch)
    return total
