"""
Tests for the Firestore history sync.

The web app reads prices from two stores, so correcting RTDB alone leaves the
company page reporting figures from the stale Firestore copy. These pin that
the rebuild is derived from RTDB and carries the full history.
"""
import pytest

from pipeline.scripts.sync_firestore_history import (
    build_history,
    build_update,
    compare,
)


def node(pairs: dict) -> dict:
    return {d: {"c": c, "o": c, "h": c, "l": c} for d, c in pairs.items()}


def test_history_is_ordered_oldest_first():
    h = build_history(node({"2007-01-03": 5.0, "2007-01-02": 4.0}))
    assert [p["date"] for p in h] == ["2007-01-02", "2007-01-03"]


def test_full_history_is_carried_across():
    """SMER starts 2007-01-02; nothing may be truncated."""
    h = build_history(node({"2007-01-02": 4.0, "2020-06-01": 3.0, "2026-08-07": 19.3}))
    assert h[0]["date"] == "2007-01-02"
    assert h[-1]["date"] == "2026-08-07"
    assert len(h) == 3


def test_rows_without_a_usable_close_are_skipped():
    n = node({"2020-01-01": 5.0})
    n["2020-01-02"] = {"c": None}
    n["2020-01-03"] = {"c": 0}
    n["2020-01-06"] = "not a dict"
    assert [p["date"] for p in build_history(n)] == ["2020-01-01"]


def test_update_derives_current_price_from_the_latest_close():
    u = build_update(node({"2026-08-06": 18.0, "2026-08-07": 19.3}))
    assert u["current_price"] == 19.3
    assert u["price_date"] == "2026-08-07"


def test_preview_is_the_last_thirty_closes():
    u = build_update(node({f"2026-01-{d:02d}": float(d) for d in range(1, 32)}))
    assert len(u["price_preview"]) == 30
    assert u["price_preview"][-1] == 31.0


def test_update_touches_only_price_fields():
    """Signals, snapshots and technicals must be left alone."""
    u = build_update(node({"2026-08-07": 19.3}))
    assert set(u) == {"price_history", "price_preview", "current_price", "price_date"}


def test_empty_node_yields_no_update():
    assert build_update({}) is None


def test_compare_counts_corrected_points():
    existing = [{"date": "2020-01-01", "price": 0.30}]
    rebuilt = [{"date": "2020-01-01", "price": 3.00}]
    d = compare(existing, rebuilt)
    assert d["changed"] == 1
    assert d["sample"] == [("2020-01-01", 0.30, 3.00)]


def test_compare_handles_a_missing_existing_history():
    d = compare(None, [{"date": "2020-01-01", "price": 3.0}])
    assert d["before_points"] == 0 and d["added"] == 1
