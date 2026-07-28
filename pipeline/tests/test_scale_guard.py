import pytest

from pipeline.scripts.scale_guard import check_scale, median_reference


def test_median_reference_odd_count():
    assert median_reference([1.0, 3.0, 2.0]) == pytest.approx(2.0)


def test_median_reference_even_count():
    assert median_reference([1.0, 2.0, 3.0, 4.0]) == pytest.approx(2.5)


def test_median_reference_ignores_zero_and_none_like_values():
    assert median_reference([0.0, 5.0, -1.0, 5.0]) == pytest.approx(5.0)


def test_median_reference_empty_returns_none():
    assert median_reference([]) is None


def test_normal_move_within_band_is_ok():
    # Reference ~35.6 (SCOM-like), a normal day-over-day move to 35.95
    result = check_scale(35.85, 35.95, 35.8, 35.95, reference_close=35.6)
    assert result.status == "ok"
    assert result.close == pytest.approx(35.95)


def test_large_but_plausible_move_is_left_alone():
    # A genuine ~2.5x move — outside OK_BAND but not a clean decimal-shift
    # error either. This guard must not touch it; that's spike-detection's job.
    result = check_scale(10.0, 11.0, 9.5, 10.5, reference_close=5.0)
    assert result.status == "ok"
    assert result.close == pytest.approx(10.5)


def test_uniform_100x_inflation_is_corrected_like_cic():
    # Mirrors the real CIC case: OCR read the whole row 100x too high, but
    # the row is internally consistent, so peer-comparison alone can't see it.
    result = check_scale(open_=460.0, high=470.0, low=453.0, close=465.0, reference_close=4.68)
    assert result.status == "corrected"
    assert result.factor == pytest.approx(100)
    assert result.close == pytest.approx(4.65)
    assert result.low <= result.open <= result.high
    assert result.low <= result.close <= result.high


def test_uniform_100x_deflation_is_corrected():
    result = check_scale(open_=4.6, high=4.7, low=4.53, close=4.65, reference_close=468.0)
    assert result.status == "corrected"
    assert result.factor == pytest.approx(0.01)
    assert result.close == pytest.approx(465.0)


def test_internally_broken_row_is_quarantined_not_forced_like_eabl():
    # Mirrors the real EABL case: close(2.73) > high(2.0) even before rescaling —
    # no uniform factor can produce a valid OHLC row, so this must quarantine,
    # never invent a value.
    result = check_scale(open_=2.73, high=2.0, low=1.67, close=2.73, reference_close=265.0)
    assert result.status == "quarantine"


def test_small_ordering_violation_is_quarantined_not_forced_like_kukz():
    # Mirrors the real KUKZ case: close(4.3) < low(4.375) — a small ordering
    # violation that persists at any scale, so it must quarantine.
    result = check_scale(open_=4.3, high=5.0, low=4.375, close=4.3, reference_close=433.5)
    assert result.status == "quarantine"


def test_no_reference_available_passes_through_unchanged():
    result = check_scale(1.0, 1.1, 0.9, 1.0, reference_close=None)
    assert result.status == "ok"
    assert result.close == pytest.approx(1.0)


def test_never_writes_a_value_it_did_not_derive_from_input():
    # Quarantine must return the ORIGINAL values, not a guess.
    result = check_scale(open_=2.73, high=2.0, low=1.67, close=2.73, reference_close=265.0)
    assert result.open == pytest.approx(2.73)
    assert result.high == pytest.approx(2.0)
    assert result.low == pytest.approx(1.67)
    assert result.close == pytest.approx(2.73)
