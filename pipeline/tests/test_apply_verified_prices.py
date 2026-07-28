import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from pipeline.scripts import apply_verified_prices as avp


def _write_history_csv(path, rows):
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)


def test_recent_closes_excludes_stale_and_future_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    _write_history_csv(tmp_path / "ABC_NR_cleaned.csv", [
        {"Date": "2026-07-20", "Open": 10, "High": 10, "Low": 10, "Close": 10.0, "Volume": 100, "Is_Stale": 0, "Ticker": "ABC"},
        {"Date": "2026-07-21", "Open": 11, "High": 11, "Low": 11, "Close": 11.0, "Volume": 0,   "Is_Stale": 1, "Ticker": "ABC"},
        {"Date": "2026-07-22", "Open": 12, "High": 12, "Low": 12, "Close": 12.0, "Volume": 50,  "Is_Stale": 0, "Ticker": "ABC"},
        {"Date": "2026-07-28", "Open": 99, "High": 99, "Low": 99, "Close": 99.0, "Volume": 50,  "Is_Stale": 0, "Ticker": "ABC"},
    ])
    history = avp.load_history("ABC")
    closes = avp.recent_closes(history, datetime.date(2026, 7, 23))
    assert closes == [10.0, 12.0]  # stale row and future row both excluded


def test_recent_closes_no_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    assert avp.recent_closes(avp.load_history("NOPE"), datetime.date(2026, 7, 23)) == []


def test_next_day_prev_close_reads_corroborating_value():
    fields = {"XYZ": {"prev_close": 45.5, "close": 46.0}}
    assert avp.next_day_prev_close("XYZ", fields) == pytest.approx(45.5)


def test_next_day_prev_close_missing_ticker_returns_none():
    assert avp.next_day_prev_close("XYZ", {"OTHER": {"prev_close": 1.0}}) is None
    assert avp.next_day_prev_close("XYZ", None) is None


def _fields(open_, high, low, close, prev_close, volume=1000):
    return {
        "open": open_, "high": high, "low": low, "close": close,
        "prev_close": prev_close, "volume": volume, "change": 0.0, "pct_change": 0.0, "value": 0.0,
    }


def test_apply_prices_writes_clean_row_and_corrects_scale_error(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)

    # KCB-like: normal ticker, no scale issue.
    _write_history_csv(tmp_path / "KCB_NR_cleaned.csv", [
        {"Date": "2026-07-24", "Open": 82.0, "High": 82.0, "Low": 82.0, "Close": 82.0, "Volume": 100, "Is_Stale": 0, "Ticker": "KCB"},
    ])
    # CIC-like: history around ~4.6-4.7, PDF read comes in 100x inflated.
    _write_history_csv(tmp_path / "CIC_NR_cleaned.csv", [
        {"Date": "2026-07-22", "Open": 4.60, "High": 4.70, "Low": 4.53, "Close": 4.62, "Volume": 100, "Is_Stale": 0, "Ticker": "CIC"},
        {"Date": "2026-07-23", "Open": 4.56, "High": 4.70, "Low": 4.50, "Close": 4.56, "Volume": 100, "Is_Stale": 0, "Ticker": "CIC"},
        {"Date": "2026-07-24", "Open": 4.70, "High": 4.70, "Low": 4.55, "Close": 4.68, "Volume": 100, "Is_Stale": 0, "Ticker": "CIC"},
    ])

    fake_rows = [
        ("KCB", _fields(82.25, 82.5, 82.0, 82.25, 82.0)),
        ("CIC", _fields(460.0, 470.0, 453.0, 465.0, 468.0)),
    ]

    with patch.object(avp, "extract_price_rows", return_value=fake_rows):
        report = avp.apply_prices(datetime.date(2026, 7, 27), pdf_bytes=b"fake")

    assert set(report["written"]) == {"KCB", "CIC"}
    assert report["quarantined"] == []
    assert len(report["corrected"]) == 1
    assert report["corrected"][0]["ticker"] == "CIC"

    kcb_out = pd.read_csv(tmp_path / "KCB_NR_cleaned.csv")
    assert kcb_out.iloc[-1]["Close"] == pytest.approx(82.25)
    assert kcb_out.iloc[-1]["Ticker"] == "KCB"

    cic_out = pd.read_csv(tmp_path / "CIC_NR_cleaned.csv")
    assert cic_out.iloc[-1]["Close"] == pytest.approx(4.65)  # corrected, not the raw 465.0


def test_apply_prices_quarantines_internally_broken_row_like_eabl(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    _write_history_csv(tmp_path / "EABL_NR_cleaned.csv", [
        {"Date": "2026-07-23", "Open": 266.0, "High": 270.0, "Low": 250.0, "Close": 266.0, "Volume": 100, "Is_Stale": 0, "Ticker": "EABL"},
        {"Date": "2026-07-24", "Open": 266.0, "High": 266.0, "Low": 266.0, "Close": 266.0, "Volume": 0,   "Is_Stale": 0, "Ticker": "EABL"},
    ])
    # Close(2.73) > High(2.0) even before rescaling — mirrors the real bug.
    fake_rows = [("EABL", _fields(2.73, 2.0, 1.67, 2.73, 2.75))]

    with patch.object(avp, "extract_price_rows", return_value=fake_rows):
        report = avp.apply_prices(datetime.date(2026, 7, 27), pdf_bytes=b"fake", dry_run=True)

    assert report["written"] == []
    assert len(report["quarantined"]) == 1
    assert report["quarantined"][0]["ticker"] == "EABL"

    # dry_run=True must not touch the CSV at all.
    unchanged = pd.read_csv(tmp_path / "EABL_NR_cleaned.csv")
    assert len(unchanged) == 2


def test_next_day_corroboration_resolves_newly_listed_ticker_with_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    # No CSV at all yet for this ticker (freshly listed) — only signal available
    # is the next day's PDF independently reporting the same prev_close.
    fake_today = [("NEWCO", _fields(1.20, 1.25, 1.18, 1.22, 1.19))]
    fake_next_day = {"NEWCO": {"prev_close": 1.22}}

    with patch.object(avp, "extract_price_rows", side_effect=lambda pdf_bytes, resolution=250: (
        fake_today if pdf_bytes == b"today" else list(fake_next_day.items())
    )):
        report = avp.apply_prices(
            datetime.date(2026, 7, 27), pdf_bytes=b"today",
            next_day_pdf_bytes=b"next",
        )

    assert report["written"] == ["NEWCO"]
    assert report["quarantined"] == []
    out = pd.read_csv(tmp_path / "NEWCO_NR_cleaned.csv")
    assert out.iloc[-1]["Close"] == pytest.approx(1.22)
