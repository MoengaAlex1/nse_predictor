import sys
import io
import logging
import warnings
import pandas as pd
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller
import joblib
from pathlib import Path
from config import MODELS_DIR

log = logging.getLogger(__name__)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _select_order(series: pd.Series, default: tuple = (2, 1, 2)) -> tuple:
    """Auto-select differencing order d via ADF test; p and q stay fixed."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = adfuller(series.dropna())
    p_value = result[1]
    d = 0 if p_value <= 0.05 else 1
    return (default[0], d, default[2])


def check_stationarity(series: pd.Series) -> tuple[float, float]:
    result = adfuller(series.dropna())
    adf_stat, p_value = result[0], result[1]
    log.info("ADF Statistic: %.4f | p-value: %.4f", adf_stat, p_value)
    if p_value > 0.05:
        log.info("Series is non-stationary -> d=1 differencing will be applied")
    return adf_stat, p_value


def train_arima(series: pd.Series, order: tuple | None = None) -> object:
    """
    Fit ARIMA to `series`. If order is None, auto-selects d via ADF test.
    Suppresses convergence warnings common with small/stale NSE series.
    """
    if order is None:
        order = _select_order(series)
    log.info("[ARIMA] Fitting ARIMA%s on %d observations...", order, len(series))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitted = ARIMA(series, order=order).fit()
    log.info("AIC=%.2f  BIC=%.2f", fitted.aic, fitted.bic)
    return fitted


def arima_forecast(fitted_model, steps: int = 30) -> pd.Series:
    """Return `steps` ahead in-sample forecast as a Series."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return fitted_model.forecast(steps=steps)


def arima_forecast_with_ci(fitted_model, steps: int = 30, alpha: float = 0.05) -> pd.DataFrame:
    """
    Returns DataFrame with columns [forecast, lower_ci, upper_ci].
    alpha=0.05 → 95% prediction intervals.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        pred = fitted_model.get_forecast(steps=steps)
    summary = pred.summary_frame(alpha=alpha)
    return pd.DataFrame({
        "forecast":  summary["mean"],
        "lower_ci":  summary["mean_ci_lower"],
        "upper_ci":  summary["mean_ci_upper"],
    })


def arima_predict_test(
    series: pd.Series,
    train_split: float = 0.80,
    order: tuple | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Fit ARIMA on training portion and evaluate on test set.
    Returns (predictions_array, actuals_array).
    """
    split = int(len(series) * train_split)
    train, test = series.iloc[:split], series.iloc[split:]
    fitted = train_arima(train, order=order)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        preds = fitted.forecast(steps=len(test))
    return preds.values, test.values


def save_arima(fitted_model, ticker: str, model_dir: Path = MODELS_DIR) -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"{ticker.replace('.', '_')}_arima.pkl"
    joblib.dump(fitted_model, path)
    log.info("ARIMA saved -> %s", path.name)
    return path


def load_arima(ticker: str, model_dir: Path = MODELS_DIR):
    path = model_dir / f"{ticker.replace('.', '_')}_arima.pkl"
    return joblib.load(path)
