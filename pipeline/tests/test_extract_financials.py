import pytest
from pipeline.scripts.extract_financials import (
    clean_value, parse_unit, build_metric, EMPTY_FINANCIALS,
)


def test_clean_value_strips_commas_and_parentheses():
    assert clean_value("(1,340)") == pytest.approx(-1340.0)
    assert clean_value("18,860")  == pytest.approx(18860.0)
    assert clean_value("2.98Bn")  == pytest.approx(2.98)
    assert clean_value("-")       is None
    assert clean_value("n/a")     is None


def test_parse_unit_detects_bn_mn():
    assert parse_unit("18.86 Bn") == "Bn"
    assert parse_unit("97.00 Mn") == "Mn"
    assert parse_unit("30.75")    == "KES"


def test_build_metric_structure():
    m = build_metric(current=18.86, prior=18.49, unit="Bn", currency="KES")
    assert m["current"]  == pytest.approx(18.86)
    assert m["prior"]    == pytest.approx(18.49)
    assert m["yoy_pct"]  == pytest.approx(2.0, rel=0.1)
    assert m["unit"]     == "Bn"
    assert m["currency"] == "KES"


def test_build_metric_with_null_prior():
    m = build_metric(current=18.86, prior=None, unit="Bn", currency="KES")
    assert m["yoy_pct"] is None


def test_empty_financials_has_all_required_keys():
    ef = EMPTY_FINANCIALS()
    assert "income_statement" in ef
    assert "gross_revenue" in ef["income_statement"]
    assert "cash_flow" in ef
    assert "cash_at_period_end" in ef["cash_flow"]
    assert "returns" in ef
    assert "annualised_roe" in ef["returns"]
