"""
Tests for the intraday price push.

The contract this protects: the live scrape keeps writing current_price on
every run exactly as it always has (that is how PDF-verified closes reach
Firestore after settlement), while the *status* it writes never downgrades a
day the official PDF has already settled.
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from pipeline.scripts import push_intraday_prices as pip_mod
from pipeline.scripts.price_status import FINAL, PROVISIONAL

COMPANY = {"ticker": "SCOM.NR", "short": "SCOM"}


@pytest.fixture
def price_df() -> pd.DataFrame:
    """Two trading days of closes: 28.00 then 28.40 (+1.43%)."""
    return pd.DataFrame(
        {"Close": [28.00, 28.40]},
        index=pd.to_datetime(["2026-08-06", "2026-08-07"]),
    )


def _fake_db(existing: dict | None):
    """Firestore double whose company doc returns `existing`."""
    db = MagicMock()
    snap = MagicMock()
    snap.exists = existing is not None
    snap.to_dict = MagicMock(return_value=existing or {})
    db.collection.return_value.document.return_value.get.return_value = snap
    return db


def _run(monkeypatch, price_df, existing: dict | None) -> dict:
    """Call push_company with the CSV read and Firestore write stubbed; return the payload."""
    monkeypatch.setattr(pip_mod, "_get_csv", lambda safe: price_df)

    captured: dict = {}
    monkeypatch.setattr(
        pip_mod,
        "update_company_public",
        lambda db, doc_id, payload: captured.update({"doc_id": doc_id, **payload}),
    )

    result = pip_mod.push_company(COMPANY, _fake_db(existing))
    assert result["pushed"] is True
    return captured


# --------------------------------------------------------------------------
# Regression lock: the pre-existing payload must not change shape
# --------------------------------------------------------------------------

# Exactly the keys this script wrote before provisional/final was introduced.
# Anything removed from or renamed in this set is a breaking change to data the
# web app already reads.
LEGACY_KEYS = {
    "current_price",
    "change_pct_today",
    "price_history",
    "price_preview",
    "last_updated",
    "intraday_today",
    "intraday_date",
}

STATUS_KEYS = {"price_status", "price_status_date", "price_source", "price_as_of"}


def test_all_legacy_keys_still_written(monkeypatch, price_df):
    payload = _run(monkeypatch, price_df, existing=None)
    assert LEGACY_KEYS <= set(payload)


def test_adds_only_status_keys_and_nothing_else(monkeypatch, price_df):
    """The change must be purely additive — no new surprise fields."""
    payload = _run(monkeypatch, price_df, existing=None)
    added = set(payload) - LEGACY_KEYS - {"doc_id"}
    assert added == STATUS_KEYS


def test_legacy_keys_written_even_after_settlement(monkeypatch, price_df):
    existing = {"price_status": FINAL, "price_status_date": pip_mod.TODAY_EAT}
    payload = _run(monkeypatch, price_df, existing)
    assert LEGACY_KEYS <= set(payload)


# --------------------------------------------------------------------------
# Price fields: unchanged behaviour, written on every run
# --------------------------------------------------------------------------

def test_writes_price_fields_when_provisional(monkeypatch, price_df):
    payload = _run(monkeypatch, price_df, existing=None)
    assert payload["doc_id"] == "SCOM"
    assert payload["current_price"] == 28.40
    assert payload["change_pct_today"] == pytest.approx(1.4286, abs=1e-3)
    assert payload["price_history"][-1] == {"date": "2026-08-07", "price": 28.40}
    assert payload["price_preview"][-1] == 28.40
    assert payload["last_updated"] == pip_mod.TODAY


def test_still_writes_price_fields_after_settlement(monkeypatch, price_df):
    """
    Settlement must not freeze current_price: apply_verified_prices corrects the
    CSVs from the PDF, and this push is how those corrections reach Firestore.
    """
    existing = {"price_status": FINAL, "price_status_date": pip_mod.TODAY_EAT}
    payload = _run(monkeypatch, price_df, existing)
    assert payload["current_price"] == 28.40
    assert payload["change_pct_today"] == pytest.approx(1.4286, abs=1e-3)


def test_change_pct_capped_at_circuit_breaker(monkeypatch):
    """NSE circuit breaker is +/-15%; a bad scrape must not report 400%."""
    df = pd.DataFrame(
        {"Close": [10.00, 90.00]},
        index=pd.to_datetime(["2026-08-06", "2026-08-07"]),
    )
    payload = _run(monkeypatch, df, existing=None)
    assert payload["change_pct_today"] == 15.0


# --------------------------------------------------------------------------
# Status fields: the no-downgrade guard
# --------------------------------------------------------------------------

def test_marks_provisional_on_a_fresh_doc(monkeypatch, price_df):
    payload = _run(monkeypatch, price_df, existing=None)
    assert payload["price_status"] == PROVISIONAL
    assert payload["price_status_date"] == pip_mod.TODAY_EAT
    assert payload["price_as_of"] == pip_mod.TIME_EAT


def test_does_not_downgrade_a_settled_day(monkeypatch, price_df):
    """A live scrape landing after the PDF must leave the day FINAL."""
    existing = {"price_status": FINAL, "price_status_date": pip_mod.TODAY_EAT}
    payload = _run(monkeypatch, price_df, existing)
    assert "price_status" not in payload
    assert "price_source" not in payload


def test_new_day_starts_provisional_after_a_settled_day(monkeypatch, price_df):
    existing = {"price_status": FINAL, "price_status_date": "2026-08-06"}
    payload = _run(monkeypatch, price_df, existing)
    assert payload["price_status"] == PROVISIONAL
    assert payload["price_status_date"] == pip_mod.TODAY_EAT


def test_reprovisions_over_an_earlier_provisional_run(monkeypatch, price_df):
    existing = {"price_status": PROVISIONAL, "price_status_date": pip_mod.TODAY_EAT}
    payload = _run(monkeypatch, price_df, existing)
    assert payload["price_status"] == PROVISIONAL


# --------------------------------------------------------------------------
# Intraday accumulation: unchanged behaviour
# --------------------------------------------------------------------------

def test_intraday_points_accumulate_and_stay_idempotent(monkeypatch, price_df):
    """
    Re-running in the same minute replaces rather than duplicates the point.

    TIME_EAT is pinned rather than taken from the clock. The module computes it
    at import, so a test asserting order against a live TIME_EAT passes during
    market hours and fails overnight — this test broke at 00:45 EAT, when
    TIME_EAT sorts before the "09:00" fixture entry.
    """
    monkeypatch.setattr(pip_mod, "TIME_EAT", "13:00")
    existing = {
        "intraday_date": pip_mod.TODAY_EAT,
        "intraday_today": [
            {"time": "09:00", "price": 28.10},
            {"time": "13:00", "price": 28.20},
        ],
    }
    payload = _run(monkeypatch, price_df, existing)
    points = payload["intraday_today"]
    assert [p["time"] for p in points] == ["09:00", "13:00"]
    assert points[-1]["price"] == 28.40
    assert payload["intraday_date"] == pip_mod.TODAY_EAT


def test_intraday_points_stay_sorted_regardless_of_run_time(monkeypatch, price_df):
    """An early-morning run must slot in before, not after, a later snapshot."""
    monkeypatch.setattr(pip_mod, "TIME_EAT", "09:05")
    existing = {
        "intraday_date": pip_mod.TODAY_EAT,
        "intraday_today": [{"time": "14:00", "price": 28.90}],
    }
    payload = _run(monkeypatch, price_df, existing)
    assert [p["time"] for p in payload["intraday_today"]] == ["09:05", "14:00"]


def test_intraday_records_a_point_even_after_settlement(monkeypatch, price_df):
    """The 1D chart should stay complete regardless of status."""
    existing = {
        "price_status": FINAL,
        "price_status_date": pip_mod.TODAY_EAT,
        "intraday_date": pip_mod.TODAY_EAT,
        "intraday_today": [{"time": "09:00", "price": 28.10}],
    }
    payload = _run(monkeypatch, price_df, existing)
    assert len(payload["intraday_today"]) == 2


def test_previous_day_intraday_is_archived_not_carried_over(monkeypatch, price_df):
    existing = {
        "intraday_date": "2026-08-06",
        "intraday_today": [{"time": "09:00", "price": 27.50}],
    }
    payload = _run(monkeypatch, price_df, existing)
    assert [p["time"] for p in payload["intraday_today"]] == [pip_mod.TIME_EAT]
