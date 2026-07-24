import datetime
import pytest
from unittest.mock import MagicMock, patch


SAMPLE_ROW = ["28.20", "28.30", "28.50", "27.90", "28.40", "0.20", "0.71", "15234100", "431654240"]


def test_parse_price_row_extracts_all_fields():
    from pipeline.scripts.scrape_nse_pdf import parse_price_row
    result = parse_price_row(SAMPLE_ROW)
    assert result["prev_close"]  == pytest.approx(28.20, rel=1e-3)
    assert result["open"]        == pytest.approx(28.30, rel=1e-3)
    assert result["high"]        == pytest.approx(28.50, rel=1e-3)
    assert result["low"]         == pytest.approx(27.90, rel=1e-3)
    assert result["close"]       == pytest.approx(28.40, rel=1e-3)
    assert result["change"]      == pytest.approx(0.20,  rel=1e-3)
    assert result["pct_change"]  == pytest.approx(0.71,  rel=1e-2)
    assert result["volume"]      == pytest.approx(15234100.0, rel=1e-3)
    assert result["value"]       == pytest.approx(431654240.0, rel=1e-3)


def test_parse_price_row_handles_zero_volume():
    from pipeline.scripts.scrape_nse_pdf import parse_price_row
    row = ["42.00", "0", "0", "0", "42.00", "0.00", "0.00", "0", "0"]
    result = parse_price_row(row)
    assert result["volume"] == 0.0
    assert result["close"]  == pytest.approx(42.00, rel=1e-3)


def test_clean_number_handles_commas():
    from pipeline.scripts.scrape_nse_pdf import clean_number
    assert clean_number("15,234,100") == pytest.approx(15234100.0)
    assert clean_number("0.71%")      == pytest.approx(0.71)
    assert clean_number("0")          == pytest.approx(0.0)


def test_pdf_url_format():
    from pipeline.scripts.scrape_nse_pdf import build_pdf_url
    url = build_pdf_url(datetime.date(2026, 7, 24))
    assert url == "https://www.nse.co.ke/wp-content/uploads/24-JUL-26.pdf"


def test_resolve_ticker_known_company():
    from pipeline.scripts.scrape_nse_pdf import resolve_ticker
    assert resolve_ticker("SAFARICOM LIMITED") == "SCOM"
    assert resolve_ticker("KCB GROUP PLC")     == "KCB"
    assert resolve_ticker("BAT KENYA LIMITED") == "BAT"


def test_resolve_ticker_unknown_returns_none():
    from pipeline.scripts.scrape_nse_pdf import resolve_ticker
    assert resolve_ticker("UNKNOWN COMPANY XYZ") is None


def test_write_to_rtdb_dry_run_no_writes():
    from pipeline.scripts.scrape_nse_pdf import write_to_rtdb
    root = MagicMock()
    rows = [("SAFARICOM", {"open": 28.3, "high": 28.5, "low": 27.9, "close": 28.4,
                            "volume": 1e6, "prev_close": 28.2, "change": 0.2,
                            "pct_change": 0.71, "value": 4.3e8})]
    count = write_to_rtdb(root, "2026-07-24", rows, dry_run=True)
    assert count == 1
    root.update.assert_not_called()
