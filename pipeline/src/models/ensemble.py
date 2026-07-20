import logging
import numpy as np
from config import ENSEMBLE_WEIGHTS, NSE_DAILY_BAND_PCT

log = logging.getLogger(__name__)


def ensemble_predict(
    lstm_pred: np.ndarray,
    xgb_pred: np.ndarray,
    arima_pred: np.ndarray,
    weights: tuple = ENSEMBLE_WEIGHTS,
) -> np.ndarray:
    w_lstm, w_xgb, w_arima = weights
    n = min(len(lstm_pred), len(xgb_pred), len(arima_pred))
    return (
        w_lstm  * lstm_pred[:n]  +
        w_xgb   * xgb_pred[:n]  +
        w_arima * arima_pred[:n]
    )


def generate_signal(
    current_price: float,
    predicted_price: float,
    var_pct: float,
) -> dict:
    pct_change = (predicted_price - current_price) / current_price * 100
    # Enforce NSE daily band limit
    pct_change = max(-NSE_DAILY_BAND_PCT, min(NSE_DAILY_BAND_PCT, pct_change))

    if pct_change > 2.0:
        signal    = "BUY"
        rationale = f"Model predicts +{pct_change:.2f}% gain"
    elif pct_change < -2.0:
        signal    = "SELL"
        rationale = f"Model predicts {pct_change:.2f}% decline"
    else:
        signal    = "HOLD"
        rationale = f"Model predicts marginal move ({pct_change:.2f}%)"

    # Risk-adjusted override: if predicted gain is smaller than VaR loss, stay out
    risk_signal = signal if abs(pct_change) > abs(var_pct) else "HOLD"

    return {
        "signal":               signal,
        "risk_adjusted_signal": risk_signal,
        "current_price_KES":    round(current_price, 2),
        "predicted_price_KES":  round(predicted_price, 2),
        "predicted_change_pct": round(pct_change, 2),
        "var_95_pct":           round(var_pct, 2),
        "rationale":            rationale,
    }


def compute_ensemble_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae  = float(mean_absolute_error(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.where(y_true == 0, 1, y_true))) * 100)
    dir_acc = float(np.mean(np.sign(np.diff(y_true)) == np.sign(np.diff(y_pred))) * 100)
    log.info("[Ensemble] RMSE: %.4f | MAE: %.4f | MAPE: %.2f%% | Dir Acc: %.1f%%", rmse, mae, mape, dir_acc)
    return {"rmse": rmse, "mae": mae, "mape": mape, "directional_accuracy": dir_acc}
