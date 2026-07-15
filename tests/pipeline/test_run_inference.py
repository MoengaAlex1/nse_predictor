# tests/pipeline/test_run_inference.py
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "pipeline"))

MOCK_DF_SHORT = pd.DataFrame(
    {
        "Open": [30.0, 31.0, 32.0],
        "High": [31.0, 32.0, 33.0],
        "Low": [29.0, 30.0, 31.0],
        "Close": [30.5, 31.5, 32.5],
        "Volume": [1000, 1100, 1200],
    },
    index=pd.date_range("2026-07-13", periods=3),
)

_rng = np.random.default_rng(42)
_prices = 30.0 + np.cumsum(_rng.normal(0, 0.3, 250))
MOCK_DF_LONG = pd.DataFrame(
    {
        "Open": _prices - 0.1,
        "High": _prices + 0.5,
        "Low": _prices - 0.5,
        "Close": _prices,
        "Volume": _rng.integers(800, 2000, 250).astype(float),
    },
    index=pd.bdate_range("2024-01-01", periods=250),
)


def test_build_company_result_has_required_keys():
    from pipeline.scripts.run_inference import build_company_result

    signal = {
        "signal": "BUY",
        "risk_adjusted_signal": "BUY",
        "current_price_KES": 32.5,
        "predicted_price_KES": 34.0,
        "predicted_change_pct": 4.6,
        "var_95_pct": -2.1,
        "rationale": "Model predicts 4.6% gain",
    }
    metrics = {"rmse": 1.2, "mae": 0.9, "mape": 3.1, "directional_accuracy": 78.0}
    actuals = np.array([30.5, 31.5, 32.5])
    preds = np.array([30.8, 31.2, 32.1])
    forecast = np.array([33.0, 33.5, 34.0])

    result = build_company_result(signal, metrics, actuals, preds, forecast)

    for key in [
        "signal",
        "risk_adjusted_signal",
        "current_price_KES",
        "predicted_price_KES",
        "predicted_change_pct",
        "var_95_pct",
        "rationale",
        "metrics",
        "actuals",
        "preds",
        "forecast",
    ]:
        assert key in result, f"Missing key: {key}"

    assert isinstance(result["actuals"], list)
    assert isinstance(result["preds"], list)
    assert isinstance(result["forecast"], list)


def test_build_technicals_result_fallback_has_required_keys():
    """3-row df triggers the fallback path — verifies fallback schema is complete."""
    from pipeline.scripts.run_inference import build_technicals_result

    result = build_technicals_result(MOCK_DF_SHORT, "2026-07-15")
    for key in [
        "rsi_14",
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_12",
        "ema_26",
        "volume",
        "daily_return",
        "monthly_heatmap",
    ]:
        assert key in result, f"Missing key in fallback: {key}"


def test_build_technicals_result_happy_path_has_required_keys():
    """250-row df exercises the real TA calculations."""
    from pipeline.scripts.run_inference import build_technicals_result

    result = build_technicals_result(MOCK_DF_LONG, "2026-07-15")
    assert "error" not in result, f"Unexpected error: {result.get('error')}"
    for key in [
        "rsi_14",
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_12",
        "ema_26",
        "volume",
        "daily_return",
        "monthly_heatmap",
    ]:
        assert key in result, f"Missing key in success path: {key}"
    assert result["rsi_14"] is not None, "rsi_14 should be non-None on 250 rows"
    assert result["sma_200"] is not None, "sma_200 should be non-None on 250 rows"
