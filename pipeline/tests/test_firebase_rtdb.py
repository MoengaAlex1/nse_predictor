import pytest
from unittest.mock import MagicMock


def _make_root_ref():
    ref = MagicMock()
    return ref


def test_write_price_node_builds_correct_path():
    from pipeline.scripts.firebase_rtdb import write_price_node
    root = _make_root_ref()
    write_price_node(root, "SCOM", "2024-01-02", {
        "o": 28.0, "h": 28.5, "l": 27.5, "c": 28.2,
        "v": 1000000.0, "pc": 27.9, "ch": 0.3, "pch": 1.08, "vv": 28200000.0,
    })
    root.update.assert_called_once()
    call_args = root.update.call_args[0][0]
    assert "prices/SCOM/2024-01-02" in call_args


def test_write_price_node_zero_volume():
    from pipeline.scripts.firebase_rtdb import write_price_node
    root = _make_root_ref()
    write_price_node(root, "SCOM", "2024-01-02", {
        "o": None, "h": None, "l": None, "c": None,
        "v": 0, "pc": None, "ch": None, "pch": None, "vv": None
    })
    root.update.assert_called_once()


def test_bulk_write_batches_correctly():
    from pipeline.scripts.firebase_rtdb import bulk_write_prices
    root = _make_root_ref()
    records = {
        f"2020-01-{i:02d}": {"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0,
                              "v": 0, "pc": None, "ch": None, "pch": None, "vv": None}
        for i in range(1, 12)
    }
    total = bulk_write_prices(root, "KCB", records, batch_size=5)
    # 11 records, batch 5 → ceil(11/5) = 3 calls
    assert root.update.call_count == 3
    assert total == 11


def test_to_short_ticker():
    from pipeline.scripts.firebase_rtdb import to_short_ticker
    assert to_short_ticker("SCOM.NR") == "SCOM"
    assert to_short_ticker("SCOM_NR") == "SCOM"
    assert to_short_ticker("BAT") == "BAT"
    assert to_short_ticker("KCB.NR") == "KCB"


def test_clean_nan_returns_none():
    from pipeline.scripts.firebase_rtdb import _clean
    import math
    assert _clean(math.nan) is None
    assert _clean(math.inf) is None
    assert _clean(None) is None
    assert _clean(28.5) == pytest.approx(28.5)
