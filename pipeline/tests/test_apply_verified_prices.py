import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from pipeline.scripts import apply_verified_prices as avp


def _write_history_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)


def _fields(open_, high, low, close, prev_close, volume=1000):
    return {
        "open": open_, "high": high, "low": low, "close": close,
        "prev_close": prev_close, "volume": volume, "change": 0.0, "pct_change": 0.0, "value": 0.0,
    }


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


def test_forward_fill_row_uses_last_real_close_flat():
    history = pd.DataFrame([
        {"Date": pd.Timestamp("2026-07-23"), "Close": 10.0, "Is_Stale": 0},
        {"Date": pd.Timestamp("2026-07-24"), "Close": 12.0, "Is_Stale": 0},
    ])
    row = avp.forward_fill_row(history, datetime.date(2026, 7, 27))
    assert row == {"open": 12.0, "high": 12.0, "low": 12.0, "close": 12.0, "volume": 0.0}


def test_forward_fill_row_no_real_history_returns_none():
    empty = pd.DataFrame(columns=["Date", "Close", "Is_Stale"])
    assert avp.forward_fill_row(empty, datetime.date(2026, 7, 27)) is None
    assert avp.forward_fill_row(None, datetime.date(2026, 7, 27)) is None


def _mock_extract(responses: dict[int, list]):
    """responses maps resolution -> list of (ticker, fields) extract_price_rows would return."""
    def _side_effect(pdf_bytes, resolution=250):
        return responses.get(resolution, [])
    return _side_effect


def test_apply_prices_writes_clean_row_and_corrects_scale_error(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)

    _write_history_csv(tmp_path / "KCB_NR_cleaned.csv", [
        {"Date": "2026-07-24", "Open": 82.0, "High": 82.0, "Low": 82.0, "Close": 82.0, "Volume": 100, "Is_Stale": 0, "Ticker": "KCB"},
    ])
    _write_history_csv(tmp_path / "CIC_NR_cleaned.csv", [
        {"Date": "2026-07-22", "Open": 4.60, "High": 4.70, "Low": 4.53, "Close": 4.62, "Volume": 100, "Is_Stale": 0, "Ticker": "CIC"},
        {"Date": "2026-07-23", "Open": 4.56, "High": 4.70, "Low": 4.50, "Close": 4.56, "Volume": 100, "Is_Stale": 0, "Ticker": "CIC"},
        {"Date": "2026-07-24", "Open": 4.70, "High": 4.70, "Low": 4.55, "Close": 4.68, "Volume": 100, "Is_Stale": 0, "Ticker": "CIC"},
    ])

    primary_rows = [
        ("KCB", _fields(82.25, 82.5, 82.0, 82.25, 82.0)),
        ("CIC", _fields(460.0, 470.0, 453.0, 465.0, 468.0)),
    ]

    with patch.object(avp, "extract_price_rows", side_effect=_mock_extract({250: primary_rows})):
        report = avp.apply_prices(datetime.date(2026, 7, 27), pdf_bytes=b"fake")

    assert set(report["written"]) == {"KCB", "CIC"}
    assert report["unresolved"] == []
    assert report["forward_filled"] == []
    assert len(report["corrected"]) == 1
    assert report["corrected"][0]["ticker"] == "CIC"
    assert report["corrected"][0]["source"] == "ocr_primary"

    kcb_out = pd.read_csv(tmp_path / "KCB_NR_cleaned.csv")
    assert kcb_out.iloc[-1]["Close"] == pytest.approx(82.25)
    cic_out = pd.read_csv(tmp_path / "CIC_NR_cleaned.csv")
    assert cic_out.iloc[-1]["Close"] == pytest.approx(4.65)


def test_broken_primary_row_falls_back_to_forward_fill_like_eabl(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    _write_history_csv(tmp_path / "EABL_NR_cleaned.csv", [
        {"Date": "2026-07-23", "Open": 266.0, "High": 270.0, "Low": 250.0, "Close": 266.0, "Volume": 100, "Is_Stale": 0, "Ticker": "EABL"},
        {"Date": "2026-07-24", "Open": 266.0, "High": 266.0, "Low": 266.0, "Close": 266.0, "Volume": 0,   "Is_Stale": 0, "Ticker": "EABL"},
    ])
    # Close(2.73) > High(2.0) even before rescaling — same broken reading on both
    # the primary AND retry OCR pass (mirrors a structural PDF-layout bug, not noise).
    broken = [("EABL", _fields(2.73, 2.0, 1.67, 2.73, 2.75))]

    with patch.object(avp, "extract_price_rows", side_effect=_mock_extract({250: broken, avp.RETRY_RESOLUTION: broken})), \
         patch.object(avp, "fetch_alt_source_row", return_value=None):
        report = avp.apply_prices(datetime.date(2026, 7, 27), pdf_bytes=b"fake")

    assert report["forward_filled"] == ["EABL"]
    assert report["unresolved"] == []
    out = pd.read_csv(tmp_path / "EABL_NR_cleaned.csv")
    last = out.iloc[-1]
    assert last["Close"] == pytest.approx(266.0)  # last real close, not the garbled 2.73
    assert last["Is_Stale"] == 1
    assert last["Volume"] == 0


def test_ocr_retry_resolves_ticker_missed_at_primary_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    _write_history_csv(tmp_path / "GHI_NR_cleaned.csv", [
        {"Date": "2026-07-24", "Open": 50.0, "High": 50.0, "Low": 50.0, "Close": 50.0, "Volume": 100, "Is_Stale": 0, "Ticker": "GHI"},
    ])
    # Primary pass finds nothing for GHI at all; retry pass (different DPI) reads it fine.
    primary = []
    retry = [("GHI", _fields(50.5, 51.0, 50.0, 50.5, 50.0))]

    with patch.object(avp, "extract_price_rows", side_effect=_mock_extract({250: primary, avp.RETRY_RESOLUTION: retry})):
        report = avp.apply_prices(datetime.date(2026, 7, 27), pdf_bytes=b"fake")

    assert "GHI" in report["written"]
    assert report["unresolved"] == []
    out = pd.read_csv(tmp_path / "GHI_NR_cleaned.csv")
    assert out.iloc[-1]["Close"] == pytest.approx(50.5)


def test_alt_source_resolves_when_both_ocr_passes_miss(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    _write_history_csv(tmp_path / "JKL_NR_cleaned.csv", [
        {"Date": "2026-07-24", "Open": 20.0, "High": 20.0, "Low": 20.0, "Close": 20.0, "Volume": 100, "Is_Stale": 0, "Ticker": "JKL"},
    ])

    with patch.object(avp, "extract_price_rows", side_effect=_mock_extract({250: [], avp.RETRY_RESOLUTION: []})), \
         patch.object(avp, "fetch_alt_source_row", return_value={"open": 20.2, "high": 20.4, "low": 20.0, "close": 20.2, "volume": 500}):
        report = avp.apply_prices(datetime.date(2026, 7, 27), pdf_bytes=b"fake")

    assert "JKL" in report["written"]
    assert report["forward_filled"] == []
    out = pd.read_csv(tmp_path / "JKL_NR_cleaned.csv")
    assert out.iloc[-1]["Close"] == pytest.approx(20.2)
    assert out.iloc[-1]["Is_Stale"] == 0


def test_no_source_and_no_history_is_unresolved(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    # CSV exists (so it's a "known" ticker) but has never had a real trade —
    # nothing to forward-fill from, and no source has data either.
    _write_history_csv(tmp_path / "GHOST_NR_cleaned.csv", [
        {"Date": "2026-07-24", "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 0, "Is_Stale": 1, "Ticker": "GHOST"},
    ])

    with patch.object(avp, "extract_price_rows", side_effect=_mock_extract({250: [], avp.RETRY_RESOLUTION: []})), \
         patch.object(avp, "fetch_alt_source_row", return_value=None):
        report = avp.apply_prices(datetime.date(2026, 7, 27), pdf_bytes=b"fake")

    assert "GHOST" not in report["written"]
    assert len(report["unresolved"]) == 1
    assert report["unresolved"][0]["ticker"] == "GHOST"


def test_next_day_corroboration_resolves_newly_listed_ticker_with_no_history(tmp_path, monkeypatch):
    monkeypatch.setattr(avp, "DATA_CLEANED", tmp_path)
    # No CSV at all yet for this ticker (freshly listed) — it only appears
    # because the PDF extracted it; the only corroborating signal is the
    # next day's PDF independently reporting the same prev_close.
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
    assert report["unresolved"] == []
    out = pd.read_csv(tmp_path / "NEWCO_NR_cleaned.csv")
    assert out.iloc[-1]["Close"] == pytest.approx(1.22)
