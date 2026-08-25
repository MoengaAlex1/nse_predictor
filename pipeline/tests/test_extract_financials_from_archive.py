"""Tests for the regex-driven half of extract_financials_from_archive.py.

The AI fallback is exercised via mocks in a separate integration test —
kept out of this file so the fast unit suite doesn't touch the SDK.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# firebase_client isn't needed for extract_from_text — stub it out so the
# import chain doesn't require FIREBASE_SERVICE_ACCOUNT_JSON at test time.
sys.modules.setdefault("scripts.firebase_client", type(sys)("stub"))

from pipeline.scripts.extract_financials_from_archive import (  # noqa: E402
    extract_from_text,
    _classify_period_type,
    _confidence,
    _period_label,
)


# Sample text pulled from a typical NSE-published FY financial results PDF
_SAMPLE_FY_TEXT = """
Kenya Company Plc
Consolidated Statement of Comprehensive Income
For The Year Ended 31 December 2024

Total Revenue                                    KES 12,345,678
Profit before tax                                     3,456,789
Profit for the year                                    Kes 2,345,678
Earnings per share                                          8.72
Dividend per share                                          3.50
Book value per share                                       45.60
"""


def test_extract_annual_all_metrics() -> None:
    r = extract_from_text(_SAMPLE_FY_TEXT)
    assert r["period_end"] == "2024-12-31"
    assert r["period_type"] == "annual"
    assert r["revenue_kes_mn"] is not None
    assert r["net_income_kes_mn"] is not None
    assert r["eps"] == 8.72
    assert r["bvps"] == 45.60
    assert r["dps_kes"] == 3.50
    assert r["confidence"] == "high"
    assert r["extraction_method"] == "regex"


def test_extract_interim_h1() -> None:
    text = """
    Company Plc
    Half Year Results for the Six Months Ended 30 June 2025

    Revenue                     KES 6,789,012
    Net Profit                       1,234,567
    Earnings per share                    5.20
    """
    r = extract_from_text(text)
    assert r["period_end"] == "2025-06-30"
    assert r["period_type"] == "interim"
    assert r["confidence"] in ("medium", "high")


def test_confidence_grades() -> None:
    assert _confidence({"revenue_kes_mn": 1, "eps": 2, "bvps": 3}) == "high"
    assert _confidence({"revenue_kes_mn": 1, "eps": 2}) == "medium"
    assert _confidence({"eps": 2}) == "low"
    assert _confidence({}) == "none"


def test_period_label() -> None:
    assert _period_label("annual", "2024-12-31") == "FY2024"
    assert _period_label("interim", "2025-06-30") == "H1 2025"
    assert _period_label("interim", "2024-12-31") == "H2 2024"
    assert _period_label("annual", None) == ""


def test_classify_period_type_by_month() -> None:
    """December period-end always classifies as annual regardless of
    the surrounding keywords (Kenyan FY convention)."""
    assert _classify_period_type("half year first half interim", "2024-12-31") == "annual"
    assert _classify_period_type("full year audited annual", "2025-06-30") == "interim"


def test_classify_period_type_by_keywords() -> None:
    """When the period_end month is neither Jun nor Dec, keyword votes decide."""
    assert _classify_period_type("H1 2025 interim results", None) == "interim"
    assert _classify_period_type("FY2024 audited annual report", None) == "annual"


def test_missing_text_returns_none_confidence() -> None:
    r = extract_from_text("")
    assert r["confidence"] == "none"


def test_loss_makes_net_income_negative() -> None:
    text = """
    Loss for the year                              Kes (2,000,000)
    Revenue                                        KES 10,000,000
    Earnings per share                                       (1.50)
    Year ended 31 December 2024
    """
    r = extract_from_text(text)
    # Loss detection should sign-flip the net income.
    assert r["net_income_kes_mn"] is not None
    assert r["net_income_kes_mn"] < 0
