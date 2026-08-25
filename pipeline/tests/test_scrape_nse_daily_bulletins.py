"""Tests for the CORPORATE ACTIONS extraction patterns in
scrape_nse_daily_bulletins.py — dividends (regression), plus the new
bonus/scrip/rights/split/AGM patterns added in the M1 milestone.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pipeline.scripts.scrape_nse_daily_bulletins import extract_actions


HEADER = "CORPORATE ACTIONS:\n"


def test_dividend_extraction_regression() -> None:
    text = HEADER + (
        "B.O.C Kenya Plc Ord 5.00; KE0000000042; announced an Interim "
        "Dividend of Kes.4.00 on 21-Aug-2026; Books Closure; 21-Sep-2026; "
        "Payment date; 19-Oct-2026"
    )
    recs = extract_actions(text)
    assert len(recs) == 1
    r = recs[0]
    assert r["kind"] == "dividend"
    assert r["type"] == "interim"
    assert r["amount_kes"] == 4.00
    assert r["announcement_date"] == "2026-08-21"
    assert r["ex_date"] == "2026-09-21"
    assert r["payment_date"] == "2026-10-19"


def test_bonus_issue_extraction() -> None:
    text = HEADER + (
        "Sample Company Plc Ord 5.00; KE0000000999; announced a Bonus "
        "Issue of 1 new share for every 5 shares held on 12-Jun-2026; "
        "Books Closure; 15-Jul-2026"
    )
    recs = extract_actions(text)
    kinds = [r["kind"] for r in recs]
    assert "bonus" in kinds
    r = next(r for r in recs if r["kind"] == "bonus")
    assert r["ratio_new"] == 1
    assert r["ratio_old"] == 5
    assert r["announcement_date"] == "2026-06-12"


def test_rights_issue_extraction() -> None:
    text = HEADER + (
        "Sample Bank Plc Ord 5.00; KE0000000888; announced a Rights Issue "
        "at Kes.25.00 per share, ratio 1:4 on 10-Mar-2026; Books Closure; "
        "22-Apr-2026"
    )
    recs = extract_actions(text)
    r = next((r for r in recs if r["kind"] == "rights"), None)
    assert r is not None
    assert r["rights_price_kes"] == 25.00
    assert r["ratio_new"] == 1
    assert r["ratio_old"] == 4
    assert r["announcement_date"] == "2026-03-10"


def test_share_split_extraction() -> None:
    text = HEADER + (
        "Sample Holdings Plc Ord 5.00; KE0000000777; announced a Share "
        "Split of 5:1 on 05-Feb-2026; Books Closure; 28-Feb-2026"
    )
    recs = extract_actions(text)
    r = next((r for r in recs if r["kind"] == "split"), None)
    assert r is not None
    assert r["ratio_new"] == 5
    assert r["ratio_old"] == 1
    assert r["announcement_date"] == "2026-02-05"


def test_agm_extraction() -> None:
    text = HEADER + (
        "Sample Investment Plc Ord 5.00; KE0000000666; announced the Annual "
        "General Meeting on 15-May-2026"
    )
    recs = extract_actions(text)
    r = next((r for r in recs if r["kind"] == "agm"), None)
    assert r is not None
    assert r["meeting_date"] == "2026-05-15"
    assert r["announcement_date"] == "2026-05-15"


def test_dividend_and_bonus_dont_double_match() -> None:
    """A single line that mentions both 'Dividend' and 'Bonus' must
    produce exactly one record — whichever pattern matches first — not
    two overlapping ones."""
    text = HEADER + (
        "Some Company Plc Ord 5.00; KE0000000555; announced an Interim "
        "Dividend of Kes.2.50 on 01-Jan-2026; Books Closure; 15-Jan-2026; "
        "Payment date; 30-Jan-2026"
    )
    recs = extract_actions(text)
    assert len(recs) == 1
    assert recs[0]["kind"] == "dividend"


def test_no_corporate_actions_block() -> None:
    """If the CORPORATE ACTIONS header isn't in the text, no records
    should come back regardless of what else the page contains."""
    text = "Some random text with an announced Dividend of Kes.1.00 on 01-Jan-2026"
    assert extract_actions(text) == []


def test_dividend_over_200_kes_rejected() -> None:
    """OCR sometimes reads 'Kes.4.00' as 'Kes.400' — the sanity cap
    keeps those out of the dividends list."""
    text = HEADER + (
        "Sample Plc Ord 5.00; KE0000000444; announced a Final Dividend "
        "of Kes.500.00 on 01-Jan-2026; Books Closure; 15-Jan-2026; "
        "Payment date; 30-Jan-2026"
    )
    assert extract_actions(text) == []
