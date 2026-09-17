"""Tests for pipeline.src.analysis.indices — parser + aggregator wiring.

No network: parse fixture HTML that matches the shape of nse.co.ke's
market-statistics table.
"""

from unittest.mock import patch

from pipeline.src.analysis.indices import (
    parse_indices_html,
    fetch_market_indices,
)
from pipeline.src.analysis.market import aggregate_market_overview


# Fixture: real HTML slice captured from https://www.nse.co.ke/dataservices/market-statistics/
# — nine rows in the shape the parser expects. Keep this fixture verbatim
# so an accidental regex tightening / label rename breaks a test loudly.
FIXTURE_HTML = """
<table>
    <tr><td>NSE ALL SHARE INDEX</td>
            <td>245.91</td><td class="nsecpos"><span>0.49 <i class="fa fa-sort-asc" aria-hidden="true"></i></span></td></tr>
    <tr><td>NSE 20 SHARE INDEX</td>
            <td>4,301.86</td><td class="nsecneg"><span>-17.96 <i class="fa fa-sort-desc" aria-hidden="true"></i></span></td></tr>
    <tr><td>NSE 25 SHARE INDEX</td>
            <td>6,927.01</td><td class="nsecneg"><span>-21.17 <i class="fa fa-sort-desc" aria-hidden="true"></i></span></td></tr>
    <tr><td>NSE 10 SHARE INDEX</td>
            <td>2,703.13</td><td class="nsecneg"><span>-7.18 <i class="fa fa-sort-desc" aria-hidden="true"></i></span></td></tr>
    <tr><td>BANKING SECTOR INDEX</td>
            <td>286.20</td><td class="nsecneg"><span>-2.32 <i class="fa fa-sort-desc" aria-hidden="true"></i></span></td></tr>
    <tr><td>MARKET CAPITALIZATION (Billions)</td>
            <td>4,126.85</td><td class="nsecpos"><span>8.21 <i class="fa fa-sort-asc" aria-hidden="true"></i></span></td></tr>
    <tr><td>TOTAL SHARE TRADED</td>
            <td>21,071,471.00</td><td class="nsecneg"><span>-4,392,820.00 <i class="fa fa-sort-desc" aria-hidden="true"></i></span></td></tr>
    <tr><td>EQUITY TURNOVER</td>
            <td>1,818,181,425.58</td><td class="nsecpos"><span>854,750,499.70 <i class="fa fa-sort-asc" aria-hidden="true"></i></span></td></tr>
    <tr><td>TOTAL EQUITY DEALS</td>
            <td>13,098.00</td><td class="nsecneg"><span>-593.00 <i class="fa fa-sort-desc" aria-hidden="true"></i></span></td></tr>
</table>
"""


def test_parse_all_six_indices_present():
    out = parse_indices_html(FIXTURE_HTML)
    assert set(out.keys()) == {"NASI", "NSE20", "NSE25", "NSE10", "NSEBSI", "MCAP",
                                "VOL", "TURNOVER", "DEALS"}


def test_parse_values_match_source_exactly():
    out = parse_indices_html(FIXTURE_HTML)
    assert out["NASI"].value == 245.91
    assert out["NSE20"].value == 4301.86
    assert out["NSE10"].value == 2703.13
    assert out["NSE25"].value == 6927.01
    assert out["NSEBSI"].value == 286.20
    assert out["MCAP"].value == 4126.85


def test_signed_delta_resolves_via_css_class_not_span_text():
    """The <span> text is often unsigned; sign lives in the outer <td class>."""
    out = parse_indices_html(FIXTURE_HTML)
    assert out["NASI"].change_points == 0.49          # nsecpos → positive
    assert out["NSE20"].change_points == -17.96       # nsecneg → negative
    assert out["MCAP"].change_points == 8.21          # nsecpos → positive


def test_change_pct_computed_against_previous_close():
    """% = signed_delta / (value - signed_delta) * 100"""
    out = parse_indices_html(FIXTURE_HTML)
    # NSE 20: -17.96 / (4301.86 - -17.96) = -17.96 / 4319.82 = -0.4158%
    assert round(out["NSE20"].change_pct, 4) == -0.4158
    # NASI: 0.49 / (245.91 - 0.49) = 0.49 / 245.42 = 0.1997%
    assert round(out["NASI"].change_pct, 4) == 0.1997


def test_turnover_rows_carry_value_but_zero_pct():
    """Volume/turnover/deals don't have a `% vs previous close` interpretation."""
    out = parse_indices_html(FIXTURE_HTML)
    assert out["TURNOVER"].value == 1_818_181_425.58
    assert out["TURNOVER"].change_pct == 0.0
    assert out["VOL"].change_pct == 0.0
    assert out["DEALS"].change_pct == 0.0


def test_reading_to_dict_round_trips():
    out = parse_indices_html(FIXTURE_HTML)
    d = out["NSE20"].to_dict()
    assert d == {
        "key":           "NSE20",
        "label":         "NSE 20",
        "value":         4301.86,
        "change_points": -17.96,
        "change_pct":    -0.4158,
    }


def test_empty_html_returns_empty_dict():
    assert parse_indices_html("<html></html>") == {}


def test_malformed_row_is_skipped_not_raised():
    html = """
    <tr><td>NSE 20 SHARE INDEX</td><td>not-a-number</td><td class="nsecpos"><span>0.5</span></td></tr>
    <tr><td>NSE ALL SHARE INDEX</td><td>100.00</td><td class="nsecpos"><span>1.00</span></td></tr>
    """
    out = parse_indices_html(html)
    assert set(out.keys()) == {"NASI"}
    assert out["NASI"].value == 100.00


def test_fetch_returns_none_on_network_error():
    with patch("pipeline.src.analysis.indices.requests.get") as mock_get:
        mock_get.side_effect = Exception("DNS failure")
        assert fetch_market_indices() is None


def test_fetch_returns_dict_of_dicts_on_success():
    """The Firestore write layer serialises via json; ensure output is JSON-safe."""
    class _Resp:
        text = FIXTURE_HTML
        def raise_for_status(self): pass
    with patch("pipeline.src.analysis.indices.requests.get", return_value=_Resp()):
        result = fetch_market_indices()
    assert result is not None
    assert isinstance(result["NSE20"], dict)  # not a dataclass
    assert result["NSE20"]["value"] == 4301.86


# ─────────────────────────────────────────────────────────────────────────────
# aggregate_market_overview integration
# ─────────────────────────────────────────────────────────────────────────────

def test_aggregate_uses_supplied_indices_and_populates_legacy_nse20():
    fake = {
        "NSE20": {"key": "NSE20", "label": "NSE 20", "value": 4301.86,
                  "change_points": -17.96, "change_pct": -0.4158},
        "NASI":  {"key": "NASI",  "label": "NASI",   "value": 245.91,
                  "change_points": 0.49,   "change_pct": 0.1997},
    }
    overview = aggregate_market_overview([], "2026-09-17", indices=fake)
    assert overview["indices"] == fake
    # Legacy fields wired from indices.NSE20 so existing readers keep working.
    assert overview["nse20_value"] == 4301.86
    assert overview["nse20_change_pct"] == -0.4158


def test_aggregate_with_empty_indices_leaves_nse20_none():
    """An {} indices dict means the feed failed at write-time — don't crash."""
    overview = aggregate_market_overview([], "2026-09-17", indices={})
    assert overview["indices"] == {}
    assert overview["nse20_value"] is None
    assert overview["nse20_change_pct"] is None


def test_aggregate_calls_fetch_when_indices_arg_omitted():
    """None sentinel triggers the live fetch. Patch it so we don't hit NSE."""
    fake = {"NSE20": {"key": "NSE20", "label": "NSE 20", "value": 100.0,
                     "change_points": 1.0, "change_pct": 1.01}}
    with patch("pipeline.src.analysis.market.fetch_market_indices", return_value=fake):
        overview = aggregate_market_overview([], "2026-09-17")
    assert overview["indices"] == fake
    assert overview["nse20_value"] == 100.0
