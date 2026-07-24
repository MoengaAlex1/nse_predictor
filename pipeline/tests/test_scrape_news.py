import pytest
from unittest.mock import patch


def test_make_doc_id_is_deterministic():
    from pipeline.scripts.scrape_news import make_doc_id
    assert make_doc_id("2026-07-23", "Earnings Release") == make_doc_id("2026-07-23", "Earnings Release")
    assert make_doc_id("2026-07-23", "A") != make_doc_id("2026-07-23", "B")


def test_fetch_marketscreener_returns_list_on_error():
    from pipeline.scripts.scrape_news import fetch_marketscreener_news
    with patch("requests.get", side_effect=ConnectionError("timeout")):
        result = fetch_marketscreener_news("SCOM")
    assert isinstance(result, list)
    assert result == []


def test_parse_announcement_includes_is_pdf():
    from pipeline.scripts.scrape_news import parse_announcement
    item = parse_announcement({
        "date": "2026-07-23",
        "title": "Annual Report 2025",
        "type": "general",
        "is_pdf": True,
        "pdf_url": "https://example.com/report.pdf",
        "source": "bat.ir",
    })
    assert item["is_pdf"] is True
    assert item["pdf_url"] == "https://example.com/report.pdf"
    assert item["source"] == "bat.ir"
