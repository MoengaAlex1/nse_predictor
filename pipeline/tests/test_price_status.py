"""
Tests for the provisional → final price settlement markers.

The behaviour that matters: a live intraday scrape must never flip a day that
the official NSE PDF has already settled back to provisional, and the PDF
finalizer must never invent Firestore documents for tickers it does not know.
"""
from unittest.mock import MagicMock

from pipeline.scripts.price_status import (
    FINAL,
    PROVISIONAL,
    SOURCE_LIVE,
    SOURCE_NSE_PDF,
    final_fields,
    is_already_final,
    provisional_fields,
)

TRADING_DAY = "2026-08-07"


# --------------------------------------------------------------------------
# Field builders
# --------------------------------------------------------------------------

def test_provisional_fields_marks_live_source():
    f = provisional_fields(TRADING_DAY, as_of="13:00")
    assert f["price_status"] == PROVISIONAL
    assert f["price_status_date"] == TRADING_DAY
    assert f["price_source"] == SOURCE_LIVE
    assert f["price_as_of"] == "13:00"


def test_provisional_fields_omits_as_of_when_absent():
    assert "price_as_of" not in provisional_fields(TRADING_DAY)


def test_final_fields_marks_pdf_source_with_timestamp():
    f = final_fields(TRADING_DAY)
    assert f["price_status"] == FINAL
    assert f["price_status_date"] == TRADING_DAY
    assert f["price_source"] == SOURCE_NSE_PDF
    assert f["price_finalized_at"].startswith("2")  # ISO-8601


def test_provisional_and_final_do_not_leave_stale_keys():
    """
    Both payloads are merged into the same doc, so any key one writes and the
    other omits would persist stale. price_as_of is the only such key and it is
    only meaningful while provisional — assert we know about it deliberately.
    """
    extra_in_provisional = set(provisional_fields(TRADING_DAY, as_of="13:00")) - set(
        final_fields(TRADING_DAY)
    )
    assert extra_in_provisional == {"price_as_of"}


# --------------------------------------------------------------------------
# The no-downgrade guard
# --------------------------------------------------------------------------

def test_is_already_final_true_for_same_day_final():
    existing = {"price_status": FINAL, "price_status_date": TRADING_DAY}
    assert is_already_final(existing, TRADING_DAY) is True


def test_is_already_final_false_for_provisional_same_day():
    existing = {"price_status": PROVISIONAL, "price_status_date": TRADING_DAY}
    assert is_already_final(existing, TRADING_DAY) is False


def test_is_already_final_false_when_final_belongs_to_another_day():
    """A new trading day always starts provisional, even after a settled one."""
    existing = {"price_status": FINAL, "price_status_date": "2026-08-06"}
    assert is_already_final(existing, TRADING_DAY) is False


def test_is_already_final_false_for_missing_or_empty_doc():
    assert is_already_final(None, TRADING_DAY) is False
    assert is_already_final({}, TRADING_DAY) is False


def test_is_already_final_false_for_unlabelled_legacy_doc():
    """Docs written before this feature carry no status fields."""
    existing = {"current_price": 28.4, "last_updated": TRADING_DAY}
    assert is_already_final(existing, TRADING_DAY) is False


# --------------------------------------------------------------------------
# PDF finalizer
# --------------------------------------------------------------------------

def _row(name: str, close: float = 28.4) -> tuple[str, dict]:
    return (name, {"open": 28.3, "high": 28.5, "low": 27.9, "close": close,
                   "volume": 1e6, "prev_close": 28.2, "change": 0.2,
                   "pct_change": 0.71, "value": 4.3e8})


def test_mark_prices_final_dry_run_writes_nothing():
    from pipeline.scripts.scrape_nse_pdf import mark_prices_final
    assert mark_prices_final(TRADING_DAY, [_row("SCOM")], dry_run=True) == 1


def test_mark_prices_final_skips_unknown_tickers(monkeypatch):
    """A stray OCR match must not create a junk Firestore document."""
    from pipeline.scripts import scrape_nse_pdf

    # KCB is a real company, deliberately excluded from the patched roster, so
    # this fails if the filter is bypassed or the patch does not take effect.
    monkeypatch.setattr(
        "pipeline.config.load_companies",
        lambda: [{"short": "SCOM"}],
    )
    assert scrape_nse_pdf.mark_prices_final(
        TRADING_DAY, [_row("SCOM"), _row("KCB"), _row("ZZZZ")], dry_run=True
    ) == 1


def _fake_firestore(monkeypatch, existing_ids: list[str]) -> list[tuple[str, dict]]:
    """
    Install a push_to_firestore double. Returns the list writes are recorded to.

    `existing_ids` is what the companies collection currently contains — the
    finalizer must confine itself to those.
    """
    updates: list[tuple[str, dict]] = []

    db = MagicMock()
    db.collection.return_value.list_documents.return_value = [
        MagicMock(id=i) for i in existing_ids
    ]

    fake_module = MagicMock()
    fake_module.get_db = MagicMock(return_value=db)
    fake_module.update_company_public = (
        lambda _db, short, payload: updates.append((short, payload))
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "pipeline.scripts.push_to_firestore",
        fake_module,
    )
    return updates


def test_mark_prices_final_never_creates_a_missing_document(monkeypatch):
    """
    update_company_public uses set(merge=True), which would create a status-only
    doc with no name/ticker/sector. The web app calls c.name.toLowerCase() on
    every company in the collection, so such a doc crashes the companies page
    and global search. The finalizer must skip it instead.
    """
    from pipeline.scripts import scrape_nse_pdf

    monkeypatch.setattr(
        "pipeline.config.load_companies",
        lambda: [{"short": "SCOM"}, {"short": "KCB"}],
    )
    updates = _fake_firestore(monkeypatch, existing_ids=["SCOM"])  # KCB doc not seeded

    marked = scrape_nse_pdf.mark_prices_final(
        TRADING_DAY, [_row("SCOM"), _row("KCB")], dry_run=False
    )

    assert marked == 1
    assert [short for short, _ in updates] == ["SCOM"]


def test_mark_prices_final_writes_status_only_not_prices(monkeypatch):
    """
    Close values straight out of OCR are not yet decimal-corrected, so the
    finalizer must not push them to Firestore.
    """
    from pipeline.scripts import scrape_nse_pdf

    monkeypatch.setattr("pipeline.config.load_companies", lambda: [{"short": "SCOM"}])
    updates = _fake_firestore(monkeypatch, existing_ids=["SCOM"])

    scrape_nse_pdf.mark_prices_final(TRADING_DAY, [_row("SCOM", close=999.9)], dry_run=False)

    assert len(updates) == 1
    short, payload = updates[0]
    assert short == "SCOM"
    assert payload["price_status"] == FINAL
    assert "current_price" not in payload
    assert not any("price" in k and "status" not in k and k != "price_source"
                   and k != "price_finalized_at" for k in payload)
