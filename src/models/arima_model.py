import sys
import io
import pandas as pd
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller
import joblib
from pathlib import Path
from config import MODELS_DIR

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def check_stationarity(series: pd.Series) -> tuple[float, float]:
    result = adfuller(series.dropna())
    adf_stat, p_value = result[0], result[1]
    print(f"  ADF Statistic: {adf_stat:.4f} | p-value: {p_value:.4f}")
    if p_value > 0.05:
        print("  Series is non-stationary -> d=1 differencing will be applied")
    return adf_stat, p_value


def train_arima(series: pd.Series, order: tuple = (2, 1, 2)):
    print("\n[ARIMA] Checking stationarity...")
    check_stationarity(series)
    print(f"[ARIMA] Fitting ARIMA{order}...")
    model = ARIMA(series, order=order)
    fitted = model.fit()
    print(fitted.summary())
    return fitted


def arima_forecast(fitted_model, steps: int = 30) -> pd.Series:
    return fitted_model.forecast(steps=steps)


def arima_predict_test(series: pd.Series, train_split: float = 0.80,
                       order: tuple = (2, 1, 2)) -> tuple:
    split = int(len(series) * train_split)
    train, test = series.iloc[:split], series.iloc[split:]
    fitted = train_arima(train, order=order)
    predictions = fitted.forecast(steps=len(test))
    return predictions.values, test.values


def save_arima(fitted_model, ticker: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = MODELS_DIR / f"{ticker.replace('.', '_')}_arima.pkl"
    joblib.dump(fitted_model, path)
    print(f"  ARIMA model saved -> {path.name}")
    return path


def load_arima(ticker: str):
    path = MODELS_DIR / f"{ticker.replace('.', '_')}_arima.pkl"
    return joblib.load(path)
