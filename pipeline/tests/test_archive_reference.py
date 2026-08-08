"""
Tests for the NSE archive loader.

Date handling is the load-bearing part. The archive mixes formats across years,
and a misparse silently shifts prices onto the wrong day rather than failing —
which is exactly the defect found in the RTDB history, where 2007-2009 dates
written as M/D/YYYY were read as D/M and transposed whenever both components
were <= 12.
"""
import datetime

import pytest

from pipeline.scripts.archive_reference import (
    _parse_date,
    _parse_number,
    _normalise_headers,
)


# --------------------------------------------------------------------------
# Date formats present across the archive years
# --------------------------------------------------------------------------

def test_us_slash_format_used_by_2007_to_2009():
    """
    '1/2/2007' is 2 January, not 1 February. Proven from the files themselves:
    the second component reaches 31, so it is the day.
    """
    assert _parse_date("1/2/2007") == datetime.date(2007, 1, 2)
    assert _parse_date("12/31/2008") == datetime.date(2008, 12, 31)


def test_day_month_year_format_used_by_later_years():
    assert _parse_date("02-Jan-20") == datetime.date(2020, 1, 2)
    assert _parse_date("2-Jan-25") == datetime.date(2025, 1, 2)
    assert _parse_date("31-Oct-25") == datetime.date(2025, 10, 31)


def test_transposable_dates_resolve_the_same_way_both_years():
    """
    A date whose parts are both <= 12 is where transposition bites. 7/8/2008
    must be 8 July, and the D-Mon-YY spelling of the same day must agree.
    """
    assert _parse_date("7/8/2008") == datetime.date(2008, 7, 8)
    assert _parse_date("08-Jul-08") == datetime.date(2008, 7, 8)


def test_unparseable_date_returns_none_rather_than_guessing():
    assert _parse_date("") is None
    assert _parse_date("-") is None
    assert _parse_date("not a date") is None


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------

def test_dash_means_no_trade_not_zero():
    """A '-' close means the stock did not trade. Reading it as 0 would
    invent a price and look like a catastrophic crash."""
    assert _parse_number("-") is None
    assert _parse_number("") is None


def test_thousands_separators_are_handled():
    assert _parse_number("7,800") == 7800.0
    assert _parse_number("416,380,000") == 416380000.0


def test_percent_sign_is_stripped():
    assert _parse_number("1.50%") == pytest.approx(1.5)


def test_ordinary_numbers():
    assert _parse_number("15") == 15.0
    assert _parse_number("0.15") == pytest.approx(0.15)


# --------------------------------------------------------------------------
# Header variations across years
# --------------------------------------------------------------------------

def test_header_case_and_bom_are_normalised():
    """2007 and 2025 carry a BOM; 2024-25 use Date/Code, earlier years DATE/CODE."""
    early = _normalise_headers(["﻿DATE", "CODE", "Day Price", "Adjust"])
    late = _normalise_headers(["﻿Date", "Code", "Day Price", "Adjusted Price"])
    assert "date" in early and "code" in early
    assert "date" in late and "code" in late
    assert early["date"] == "﻿DATE"
    assert late["date"] == "﻿Date"


def test_normalise_headers_tolerates_missing_fieldnames():
    assert _normalise_headers(None) == {}
