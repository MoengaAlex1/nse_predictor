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


def test_correct_row_does_not_touch_prev_close():
    """
    A scrape that mis-reads today's close often still carries a correct pc.
    SMER 2025-11-11 arrived as c=0.15 with pc=15.00; scaling pc alongside c
    turned a correct 15.00 into 1500.00 in live data. pc is rebuilt separately.
    """
    fixed = correct_row({"c": 0.15, "o": 0.15, "h": 0.15, "l": 0.15, "pc": 15.0}, -100)
    assert fixed["c"] == pytest.approx(15.0)
    assert fixed["pc"] == 15.0          # untouched, not 1500.0


def test_rebuild_prev_close_derives_from_the_corrected_series():
    from pipeline.scripts.fix_decimal_scale import rebuild_prev_close
    node = {
        "2025-11-10": {"c": 15.0, "pc": 15.0, "ch": 0.0, "pch": 0.0},
        "2025-11-11": {"c": 0.15, "pc": 15.0, "ch": -14.85, "pch": -99.0},
        "2025-11-12": {"c": 15.0, "pc": 0.15, "ch": 14.85, "pch": 9900.0},
    }
    corrections = {"2025-11-11": {"c": 15.0, "pc": 15.0}}
    out = rebuild_prev_close(node, corrections)
    assert out["2025-11-11"]["pc"] == pytest.approx(15.0)
    assert out["2025-11-11"]["ch"] == pytest.approx(0.0)
    # the recovery day no longer points at the old corrupt close
    assert out["2025-11-12"]["pc"] == pytest.approx(15.0)
    assert out["2025-11-12"]["pch"] == pytest.approx(0.0)


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


# --------------------------------------------------------------------------
# Per-company floors (tiers)
# --------------------------------------------------------------------------

SMER_FLOOR = {"min": 1.00}


def test_floor_resolves_what_the_window_cannot():
    """
    SMER alternates between ~3.00 and ~0.30, so some windows are majority
    corrupt and the window-majority check declines them. A verified floor is
    independent evidence and settles those rows.
    """
    closes = [3.5, 0.35] * 40                      # deliberately 50/50
    node = series(closes)
    assert find_bad_rows(node) == []               # window alone: declines
    fixed = find_bad_rows(node, SMER_FLOOR)        # with the floor: resolves
    assert len(fixed) == 40
    assert all(f["after"]["c"] == pytest.approx(3.5) for f in fixed)


def test_floor_does_not_touch_values_inside_the_range():
    node = series([3.5, 3.6, 3.4, 3.5] * 20)
    assert find_bad_rows(node, SMER_FLOOR) == []


def test_the_window_still_chooses_the_factor():
    """
    A 1.00 floor is satisfied by both x10 and x100 on a 0.15 close. Only the
    prevailing price distinguishes 1.50 from 15.00.
    """
    node, bad = with_fault(15.0, 0.15, run=2)
    fixed = find_bad_rows(node, SMER_FLOOR)
    assert [f["date"] for f in fixed] == bad
    assert all(f["after"]["c"] == pytest.approx(15.0) for f in fixed)


def test_no_correction_may_land_back_outside_the_range():
    node, _ = with_fault(15.0, 0.15, run=2)
    for f in find_bad_rows(node, SMER_FLOOR):
        assert f["after"]["c"] >= SMER_FLOOR["min"]


def test_violates_floor_handles_both_bounds():
    from pipeline.scripts.fix_decimal_scale import violates_floor
    assert violates_floor(0.5, {"min": 1.0}) is True
    assert violates_floor(1.5, {"min": 1.0}) is False
    assert violates_floor(500.0, {"min": 1.0, "max": 100.0}) is True
    assert violates_floor(5.0, None) is False


def test_companies_without_a_floor_fall_back_to_window_rules():
    node, bad = with_fault(15.0, 0.15, run=2)
    assert [b["date"] for b in find_bad_rows(node, None)] == bad
