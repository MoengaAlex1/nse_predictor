"""
Tests for the decimal-scale fixer.

The rule: NSE equities move within a +/-10% daily band, so prices change
gradually and a close that is ~10x or ~100x the prevailing price is a misplaced
decimal point, not a price move.

Direction is decided from the four months either side of the suspect day. These
fixtures therefore build realistic multi-month series — a two-row fixture cannot
exercise a window-based rule, and a rule tuned to pass one would be worthless
against real data.
"""
import datetime

import pytest

from pipeline.scripts.fix_decimal_scale import (
    correct_row,
    find_bad_rows,
    is_safe_to_write,
    local_level,
    scale_error,
)

START = datetime.date(2026, 1, 5)


def series(closes: list[float], start: datetime.date = START) -> dict:
    """Build a node of consecutive weekday closes."""
    out, d = {}, start
    for c in closes:
        while d.weekday() >= 5:
            d += datetime.timedelta(days=1)
        out[d.isoformat()] = {"c": c, "o": c, "h": c, "l": c, "pc": c}
        d += datetime.timedelta(days=1)
    return out


def with_fault(base: float, fault: float, run: int = 1, n: int = 80) -> dict:
    """A flat series at `base` with `run` consecutive days set to `fault`."""
    closes = [base] * n
    mid = n // 2
    for i in range(run):
        closes[mid + i] = fault
    node = series(closes)
    dates = sorted(node)
    return node, [dates[mid + i] for i in range(run)]


# --------------------------------------------------------------------------
# The four live faults this was built for
# --------------------------------------------------------------------------

@pytest.mark.parametrize("base,wrong,expected", [
    (85.25, 0.8525, 85.25),    # EQTY  decimal lost
    (4.69, 474.0, 4.74),       # CIC   decimal gained
    (1.16, 119.0, 1.19),       # HAFR  decimal gained
    (425.0, 4.28, 428.0),      # KUKZ  decimal lost
])
def test_live_faults_are_corrected(base, wrong, expected):
    node, bad_dates = with_fault(base, wrong)
    bad = find_bad_rows(node)
    assert [b["date"] for b in bad] == bad_dates
    assert bad[0]["after"]["c"] == pytest.approx(expected, rel=1e-6)


# --------------------------------------------------------------------------
# Runs and recoveries
# --------------------------------------------------------------------------

def test_a_run_of_bad_days_is_fully_corrected():
    """SMER sat at 0.15 for three sessions between correct 15.00 days."""
    node, bad_dates = with_fault(15.0, 0.15, run=3)
    bad = find_bad_rows(node)
    assert [b["date"] for b in bad] == bad_dates
    assert all(b["after"]["c"] == pytest.approx(15.0) for b in bad)


def test_the_recovery_day_is_never_touched():
    """
    The day after a run reads as 100x its predecessor, but matches the
    prevailing level, so the median-based rule leaves it alone.
    """
    node, bad_dates = with_fault(15.0, 0.15, run=3)
    flagged = {b["date"] for b in find_bad_rows(node)}
    after_run = sorted(node)[sorted(node).index(bad_dates[-1]) + 1]
    assert after_run not in flagged


def test_a_long_run_still_resolves_while_it_stays_a_minority():
    node, bad_dates = with_fault(15.0, 0.15, run=12, n=120)
    assert [b["date"] for b in find_bad_rows(node)] == bad_dates


# --------------------------------------------------------------------------
# Real movement must survive
# --------------------------------------------------------------------------

def test_gradual_movement_is_left_alone():
    """8, 9, 10, 13, 15, 16, 19, 23, 22 — ordinary trading, repeated."""
    trend = [8, 9, 10, 13, 15, 16, 19, 23, 22]
    assert find_bad_rows(series(trend * 9)) == []


def test_a_steady_climb_is_left_alone():
    """A stock that triples over four months is real, not a decimal fault."""
    assert find_bad_rows(series([10 * (1.015 ** i) for i in range(80)])) == []


def test_a_doubling_is_not_treated_as_a_decimal_error():
    assert scale_error(20.0, 10.0) is None


def test_a_genuine_penny_stock_is_left_alone():
    assert find_bad_rows(series([0.30, 0.31, 0.29, 0.30, 0.32] * 16)) == []


# --------------------------------------------------------------------------
# The prevailing level
# --------------------------------------------------------------------------

def test_local_level_ignores_the_row_itself():
    node, bad_dates = with_fault(15.0, 0.15)
    rows = sorted(node.items())
    idx = [d for d, _ in rows].index(bad_dates[0])
    assert local_level(rows, idx) == pytest.approx(15.0)


def test_local_level_needs_enough_surrounding_history():
    rows = sorted(series([10.0, 10.0]).items())
    assert local_level(rows, 0) is None


# --------------------------------------------------------------------------
# Scale detection
# --------------------------------------------------------------------------

@pytest.mark.parametrize("close,level,factor", [
    (80.0, 8.0, 10),
    (8.0, 80.0, -10),
    (42.23, 422.3, -10),
    (424.5, 42.45, 10),
    (474.0, 4.69, 100),
    (0.8525, 85.25, -100),
])
def test_scale_error_direction(close, level, factor):
    assert scale_error(close, level) == factor


def test_scale_error_ignores_zero_and_negative():
    assert scale_error(0, 10) is None
    assert scale_error(10, 0) is None


# --------------------------------------------------------------------------
# Whole-row correction
# --------------------------------------------------------------------------

def test_every_scaled_field_moves_together():
    fixed = correct_row(
        {"c": 0.8525, "o": 0.8550, "h": 0.8600, "l": 0.8500, "pc": 0.8525, "v": 100},
        -100,
    )
    assert fixed["c"] == pytest.approx(85.25)
    assert fixed["o"] == pytest.approx(85.5)
    assert fixed["h"] == pytest.approx(86.0)
    assert fixed["l"] == pytest.approx(85.0)


def test_volume_is_not_rescaled():
    """Volume is a share count; the decimal fault is in the price."""
    assert correct_row({"c": 0.8525, "pc": 0.8525, "v": 12345}, -100)["v"] == 12345


def test_derived_fields_follow_the_corrected_price():
    fixed = correct_row({"c": 0.474, "pc": 0.469, "ch": 0.005, "pch": 1.07}, -10)
    assert fixed["c"] == pytest.approx(4.74)
    assert fixed["ch"] == pytest.approx(0.05, abs=1e-4)


# --------------------------------------------------------------------------
# The ingest guard
# --------------------------------------------------------------------------

def test_guard_blocks_a_mis_scaled_row():
    assert is_safe_to_write(0.8525, 85.25) is False
    assert is_safe_to_write(474.0, 4.69) is False


def test_guard_allows_ordinary_movement():
    assert is_safe_to_write(85.25, 85.5) is True
    assert is_safe_to_write(9.0, 8.0) is True


def test_guard_allows_the_first_ever_row():
    assert is_safe_to_write(85.25, None) is True
