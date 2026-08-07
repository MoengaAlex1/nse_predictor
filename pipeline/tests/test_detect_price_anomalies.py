"""
Tests for the price-anomaly detector.

These encode the safety requirement that matters most: a decimal-shift fixer
must not damage companies that genuinely trade at low prices. Measured from
live data, UCHM has traded as low as 0.16, HAFR 0.27, EVRD 0.61 — nine tickers
have a median under 5 KES. A naive "below 1.00 must be wrong" rule would
multiply those tenfold and corrupt exactly what it claims to repair.
"""
import datetime

import pytest

from pipeline.scripts.detect_price_anomalies import analyse_ticker

_EPOCH = datetime.date(2020, 1, 1)


def node(prices: list[float]) -> dict:
    """
    Build an RTDB-shaped node from consecutive daily closes.

    Dates must be real and calendar-sequential: the detector sorts by date
    string, so a naive f"2020-01-{n:02d}" would emit "2020-01-100" and reorder
    the series, manufacturing cliffs that are artefacts of the test.
    """
    return {
        (_EPOCH + datetime.timedelta(days=i)).isoformat(): {"c": p}
        for i, p in enumerate(prices)
    }


def verdicts(prices: list[float]) -> list[str]:
    return [a.verdict for a in analyse_ticker("TEST", node(prices))]


# --------------------------------------------------------------------------
# Must NOT touch legitimately low-priced companies
# --------------------------------------------------------------------------

def test_sustained_penny_price_is_never_flagged():
    """A company that simply trades at 0.30 forever is not corrupt."""
    assert analyse_ticker("PENNY", node([0.30, 0.31, 0.29, 0.30] * 6)) == []


def test_gradual_decline_into_penny_territory_is_not_flagged():
    """
    UCHM genuinely fell from ~20 to ~0.16 over years. A real trend never
    trips the candidate ratio because no single step is a 4x cliff.
    """
    prices = [20.0 * (0.97 ** i) for i in range(160)]  # ~20 -> ~0.16
    assert analyse_ticker("UCHM", node(prices)) == []


def test_permanent_step_down_is_not_auto_corrected():
    """
    An unbounded move is a real regime change, not corruption. The price never
    returns, so nothing may be silently multiplied back up.
    """
    prices = [10.0] * 10 + [1.0] * 10
    assert "correctable" not in verdicts(prices)


# --------------------------------------------------------------------------
# Must catch genuine multi-day decimal shifts
# --------------------------------------------------------------------------

def test_multi_day_decimal_run_is_caught():
    """
    The exact shape fix_all_decimals.py misses: a run long enough that each bad
    day's neighbour is also bad. Mirrors SMER 2025-11-11..13 (15.00 -> 0.15).
    """
    prices = [15.0] * 8 + [0.15, 0.15, 0.15] + [15.0] * 8
    found = [a for a in analyse_ticker("SMER", node(prices)) if a.verdict == "correctable"]
    assert len(found) == 1
    assert found[0].days == 3
    assert found[0].corrected_to == pytest.approx(15.0, rel=0.05)


def test_single_day_shift_still_caught():
    prices = [3.5] * 8 + [0.35] + [3.5] * 8
    found = [a for a in analyse_ticker("X", node(prices)) if a.verdict == "correctable"]
    assert len(found) == 1


# --------------------------------------------------------------------------
# Must refuse when the evidence is not clean
# --------------------------------------------------------------------------

def test_disagreeing_flanks_are_refused():
    """
    TOTL's real shape: 16.98 before, 31.25 after. The series is unstable for
    other reasons, so the gap cannot be attributed to a decimal shift.
    """
    prices = [17.0] * 8 + [4.1] * 5 + [31.0] * 8
    found = analyse_ticker("TOTL", node(prices))
    assert found and all(a.verdict == "review" for a in found)
    assert any("flanks disagree" in a.reason for a in found)


def test_non_power_of_ten_gap_is_refused():
    """A 4x dip is not a decimal error, so no correction may be proposed."""
    prices = [20.0] * 8 + [5.0] * 4 + [20.0] * 8
    found = analyse_ticker("X", node(prices))
    assert found and all(a.verdict == "review" for a in found)


def test_run_at_series_edge_is_refused():
    """With no flank on one side there is nothing to restore continuity to."""
    prices = [0.15, 0.15] + [15.0] * 10
    found = analyse_ticker("X", node(prices))
    assert all(a.verdict == "review" for a in found)


# --------------------------------------------------------------------------
# No absolute price thresholds anywhere
# --------------------------------------------------------------------------

def test_detection_is_scale_invariant():
    """
    The same shape must be judged identically whether the stock trades at 0.15
    or 1500 — proving the rule keys off local ratios, not absolute price.
    """
    shape = [1.0] * 8 + [0.1] * 3 + [1.0] * 8
    for scale in (0.15, 1.0, 15.0, 1500.0):
        scaled = [p * scale for p in shape]
        found = [a for a in analyse_ticker("S", node(scaled)) if a.verdict == "correctable"]
        assert len(found) == 1, f"scale {scale} behaved differently"
