import sys
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_db():
    """Firestore client mock — mirrors the 4-level chain in push_item:
    db.collection().document().collection().document().set()
    """
    db = MagicMock()
    terminal = (
        db.collection.return_value
        .document.return_value
        .collection.return_value
        .document.return_value
    )
    terminal.set = MagicMock()
    return db, None, terminal


def make_scraper(mock_db):
    """Import scraper with firebase patched out."""
    db, col, doc = mock_db
    with patch.dict("sys.modules", {
        "firebase_admin": MagicMock(),
        "firebase_admin.credentials": MagicMock(),
        "firebase_admin.firestore": MagicMock(),
    }):
        import importlib
        if "pipeline.scripts.scrape_news" in sys.modules:
            del sys.modules["pipeline.scripts.scrape_news"]
        import pipeline.scripts.scrape_news as m
        m.db = db
        return m


def test_parse_announcement_returns_news_item():
    row = {
        "date": "2026-07-24",
        "company": "COOP",
        "title": "H1 2026 Interim Results",
        "url": "https://nse.co.ke/filing1.pdf",
        "type": "financial_result",
    }
    from pipeline.scripts.scrape_news import parse_announcement
    item = parse_announcement(row)
    assert item["date"] == "2026-07-24"
    assert item["title"] == "H1 2026 Interim Results"
    assert item["category"] == "earnings"
    assert item["source"] == "scraper"
    assert item["url"] == "https://nse.co.ke/filing1.pdf"


def test_make_doc_id_is_deterministic():
    from pipeline.scripts.scrape_news import make_doc_id
    id1 = make_doc_id("2026-07-24", "H1 2026 Interim Results")
    id2 = make_doc_id("2026-07-24", "H1 2026 Interim Results")
    assert id1 == id2
    assert " " not in id1


def test_make_doc_id_differs_for_different_titles():
    from pipeline.scripts.scrape_news import make_doc_id
    id1 = make_doc_id("2026-07-24", "Results A")
    id2 = make_doc_id("2026-07-24", "Results B")
    assert id1 != id2


def test_push_item_calls_firestore_set(mock_db):
    m = make_scraper(mock_db)
    db, col, doc = mock_db
    item = {"date": "2026-07-24", "title": "Test", "category": "earnings",
            "body": None, "url": None, "source": "scraper"}
    m.push_item("COOP_NR", item)
    assert doc.set.called


def test_fetch_nse_returns_list_on_http_error():
    """Scraper fails gracefully per-ticker, returns empty list."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = Exception("network error")
        from pipeline.scripts.scrape_news import fetch_nse_announcements
        result = fetch_nse_announcements("COOP_NR")
        assert result == []
