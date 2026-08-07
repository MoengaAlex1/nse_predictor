"""
Tests for the physics-based price validator.

The central guarantee: this module proves an error EXISTS in a pair of values
and never claims which half is wrong. An earlier version inferred a correction
from the percentage move alone and would have rewritten correct data.
"""
from pipeline.scripts.validate_price_physics import (
    BAND_PCT,
    magnitude_from_pch,
    validate,
)


def node(rows: dict) -> dict:
    return {"TEST": rows}


# --------------------------------------------------------------------------
# The regression that matters
# --------------------------------------------------------------------------

SMER_NOV_2025 = {
    "SMER": {
        "2025-11-03": {"c": 15.00, "pc": 15.00, "pch": 0.0},
        "2025-11-04": {"c": 15.00, "pc": 15.00, "pch": -99.0},
        "2025-11-05": {"c": 15.00, "pc": 0.15,  "pch": 9900.0},
        "2025-11-06": {"c": 15.00, "pc": 15.00, "pch": 0.0},
    }
}


def test_never_proposes_a_correction():
    """
    On 2025-11-05 the close of 15.00 is correct and the prev-close of 0.15 is
    corrupt. Reading +9900% as "today is 100x too high" would rewrite a good
    15.00 down to 0.15. No finding may carry a correction.
    """
    findings = validate(SMER_NOV_2025)
    for items in findings.values():
        for f in items:
            assert "corrected_to" not in f
            assert "factor" not in f


def test_extreme_move_is_reported_as_a_pair_not_a_culprit():
    findings = validate(SMER_NOV_2025)["SMER"]
    breaches = [f for f in findings if f["check"] == "band_breach"]
    assert breaches
    for f in breaches:
        assert f["verdict"] in {"suspect_pair", "review"}
        assert "NOT determined" in f["why"] or "below the" in f["why"]


def test_magnitude_is_direction_agnostic():
    """-99% and +9900% describe the same factor-100 discrepancy."""
    assert magnitude_from_pch(-99.0) == 100
    assert magnitude_from_pch(9900.0) == 100
    assert magnitude_from_pch(-90.0) == 10
    assert magnitude_from_pch(900.0) == 10


# --------------------------------------------------------------------------
# Real moves must not be flagged as certain
# --------------------------------------------------------------------------

def test_moves_inside_the_nse_band_are_ignored():
    rows = {"T": {f"2020-01-{d:02d}": {"c": 10.0, "pc": 10.0, "pch": 5.0}
                  for d in range(1, 10)}}
    assert validate(rows) == {}


def test_ex_dividend_sized_drop_is_not_called_certain():
    """
    ABSA breaches the band on 2 May in 2019, 2023 and 2024 — a dividend date,
    not corruption. A -12% move must never reach the certain bucket.
    """
    rows = {"ABSA": {"2019-05-02": {"c": 10.5, "pc": 12.0, "pch": -12.5}}}
    found = validate(rows).get("ABSA", [])
    assert all(f["verdict"] != "suspect_pair" for f in found)


def test_band_constant_matches_the_nse_rule():
    assert BAND_PCT == 10.0


# --------------------------------------------------------------------------
# Prev-close redundancy
# --------------------------------------------------------------------------

def test_prev_close_contradiction_is_flagged():
    """CIC 2026-08-07: yesterday closed 4.69 but pc reads 469.0."""
    rows = {"CIC": {
        "2026-08-06": {"c": 4.69, "pc": 4.69, "pch": 0.0},
        "2026-08-07": {"c": 4.74, "pc": 469.0, "pch": 0.0},
    }}
    found = validate(rows)["CIC"]
    assert any(f["check"] == "prev_close_mismatch" for f in found)


def test_non_nse_tickers_are_skipped():
    """AAPL is not NSE-listed, so the daily band does not apply to it."""
    rows = {"AAPL": {"2020-03-16": {"c": 58.47, "pc": 67.10, "pch": -92.0}}}
    assert validate(rows) == {}
