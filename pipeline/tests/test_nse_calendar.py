"""
Tests for the NSE trading calendar.

The NSE trades Monday to Friday excluding Kenyan public holidays. Any coverage
or gap figure computed on raw calendar days is wrong and alarmist, so these
pin the session-counting behaviour the audit depends on.
"""
import datetime

from pipeline.scripts.nse_calendar import (
    holidays,
    is_trading_day,
    sessions_missed,
    trading_days_between,
)


# --------------------------------------------------------------------------
# Weekends
# --------------------------------------------------------------------------

def test_weekends_are_not_trading_days():
    assert is_trading_day("2026-08-07") is True    # Friday
    assert is_trading_day("2026-08-08") is False   # Saturday
    assert is_trading_day("2026-08-09") is False   # Sunday
    assert is_trading_day("2026-08-10") is True    # Monday


# --------------------------------------------------------------------------
# Fixed holidays
# --------------------------------------------------------------------------

def test_fixed_kenyan_holidays_are_closed():
    for d in ("2026-01-01", "2026-05-01", "2026-06-01",
              "2026-10-20", "2026-12-25"):
        assert is_trading_day(d) is False, d


def test_jamhuri_and_boxing_day_are_closed():
    # 2025: 12 Dec is a Friday, 26 Dec is a Friday — both weekday holidays.
    assert is_trading_day("2025-12-12") is False
    assert is_trading_day("2025-12-26") is False


# --------------------------------------------------------------------------
# Movable holidays
# --------------------------------------------------------------------------

def test_good_friday_and_easter_monday_are_closed():
    # Easter Sunday 2026 falls on 5 April.
    assert is_trading_day("2026-04-03") is False   # Good Friday
    assert is_trading_day("2026-04-06") is False   # Easter Monday
    assert is_trading_day("2026-04-07") is True    # Tuesday after


def test_easter_is_computed_per_year():
    # Easter Sunday 2024 was 31 March, so Good Friday was 29 March.
    assert is_trading_day("2024-03-29") is False
    assert datetime.date(2024, 4, 1) in holidays(2024)   # Easter Monday


# --------------------------------------------------------------------------
# Sunday observance
# --------------------------------------------------------------------------

def test_holiday_on_sunday_is_observed_on_monday():
    # 1 June 2025 (Madaraka Day) is a Sunday, so Monday 2 June is observed.
    assert datetime.date(2025, 6, 1).weekday() == 6
    assert is_trading_day("2025-06-02") is False


# --------------------------------------------------------------------------
# Moi Day was suspended 2010-2017
# --------------------------------------------------------------------------

def test_moi_day_absent_while_suspended():
    assert datetime.date(2014, 10, 10) not in holidays(2014)


def test_moi_day_present_before_and_after_suspension():
    assert datetime.date(2009, 10, 10) in holidays(2009)
    assert datetime.date(2019, 10, 10) in holidays(2019)


# --------------------------------------------------------------------------
# Session counting — the reason this module exists
# --------------------------------------------------------------------------

def test_christmas_gap_counts_sessions_not_calendar_days():
    """
    24 Dec 2025 to 2 Jan 2026 spans 9 calendar days but only 3 trading
    sessions, once the weekends, Christmas, Boxing Day and New Year come out.
    Counting calendar days would treat a normal holiday break as a data gap.
    """
    calendar_days = (datetime.date(2026, 1, 2) - datetime.date(2025, 12, 24)).days
    assert calendar_days == 9
    assert sessions_missed("2025-12-24", "2026-01-02") == 3


def test_consecutive_trading_days_have_no_missed_sessions():
    assert sessions_missed("2026-08-06", "2026-08-07") == 0


def test_weekend_alone_is_not_a_gap():
    # Friday to Monday: nothing missed.
    assert sessions_missed("2026-08-07", "2026-08-10") == 0


def test_trading_days_between_excludes_both_endpoints():
    days = trading_days_between("2026-08-07", "2026-08-12")
    assert days == [datetime.date(2026, 8, 10), datetime.date(2026, 8, 11)]


def test_a_real_gap_is_still_detected():
    """A month of missing data must not be explained away by holidays."""
    assert sessions_missed("2026-02-02", "2026-03-02") >= 18
