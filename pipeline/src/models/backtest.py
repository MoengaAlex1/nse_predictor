"""
Walk-forward backtesting for the ensemble model.
Evaluates signal quality (BUY/SELL/HOLD directional accuracy) over historical data.
"""
import warnings
import numpy as np
import pandas as pd
from typing import Any


def walk_forward_backtest(
    feature_df: pd.DataFrame,
    cleaned_df: pd.DataFrame,
    feature_cols: list,
    n_splits: int = 5,
    min_train_pct: float = 0.60,
) -> dict:
    """
    Rolling walk-forward validation across n_splits folds.

    Returns dict with per-fold and aggregate metrics:
      - rmse, mae, mape (price prediction quality)
      - directional_accuracy (sign of price change correct %)
      - signal_accuracy (BUY/SELL/HOLD correct direction %)
    """
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    import xgboost as xgb

    close = feature_df["Close"].values
    X = feature_df[feature_cols].values
    n = len(close)

    fold_size = int(n * (1 - min_train_pct) / n_splits)
    if fold_size < 20:
        return {"error": "Not enough data for walk-forward backtest", "n_splits": 0}

    fold_metrics = []

    for k in range(n_splits):
        train_end = int(n * min_train_pct) + k * fold_size
        test_start = train_end
        test_end   = min(train_end + fold_size, n)

        if test_end - test_start < 5:
            continue

        X_train, y_train = X[:train_end], close[:train_end]
        X_test,  y_test  = X[test_start:test_end], close[test_start:test_end]

        # XGBoost only (fast enough for CV)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = xgb.XGBRegressor(
                n_estimators=200, learning_rate=0.05, max_depth=5,
                subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1
            )
            model.fit(X_train, y_train, verbose=False)

        y_pred = model.predict(X_test)

        rmse    = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        mae     = float(mean_absolute_error(y_test, y_pred))
        mape    = float(np.mean(np.abs((y_test - y_pred) / np.where(y_test == 0, 1, y_test))) * 100)
        dir_acc = float(np.mean(np.sign(np.diff(y_test)) == np.sign(np.diff(y_pred))) * 100) \
                  if len(y_test) > 1 else 0.0

        # Signal accuracy: does predicted direction match actual direction?
        actual_dir   = np.sign(np.diff(y_test))
        pred_dir     = np.sign(np.diff(y_pred))
        sig_acc      = float(np.mean(actual_dir == pred_dir) * 100) if len(actual_dir) > 0 else 0.0

        fold_metrics.append({
            "fold":                 k + 1,
            "train_size":           train_end,
            "test_size":            test_end - test_start,
            "rmse":                 round(rmse, 4),
            "mae":                  round(mae, 4),
            "mape":                 round(mape, 2),
            "directional_accuracy": round(dir_acc, 1),
            "signal_accuracy":      round(sig_acc, 1),
        })

    if not fold_metrics:
        return {"error": "All folds too small", "n_splits": 0}

    def _mean(key):
        vals = [f[key] for f in fold_metrics if isinstance(f.get(key), float)]
        return round(float(np.mean(vals)), 4) if vals else None

    return {
        "n_splits":                   len(fold_metrics),
        "avg_rmse":                   _mean("rmse"),
        "avg_mae":                    _mean("mae"),
        "avg_mape":                   _mean("mape"),
        "avg_directional_accuracy":   _mean("directional_accuracy"),
        "avg_signal_accuracy":        _mean("signal_accuracy"),
        "folds":                      fold_metrics,
    }


def signal_backtest(
    close_series: pd.Series,
    predictions: np.ndarray,
    buy_threshold: float = 2.0,
    sell_threshold: float = -2.0,
) -> dict:
    """
    Simulate BUY/SELL/HOLD signals from predicted vs actual and compute P&L.
    Starting capital: 100,000 KES.
    """
    if len(predictions) < 2 or len(close_series) < len(predictions) + 1:
        return {"error": "Insufficient data for signal backtest"}

    actuals = close_series.values[-len(predictions)-1:]
    capital = 100_000.0
    shares  = 0.0
    trades  = []
    equity  = [capital]

    for i in range(len(predictions) - 1):
        current = float(actuals[i])
        pred    = float(predictions[i])
        actual_next = float(actuals[i + 1])

        if current == 0:
            continue

        pct_change = (pred - current) / current * 100
        pct_change = max(-9.9, min(9.9, pct_change))

        if pct_change > buy_threshold and shares == 0:
            shares  = capital / current
            capital = 0.0
            trades.append({"action": "BUY", "price": current, "day": i})
        elif pct_change < sell_threshold and shares > 0:
            capital = shares * current
            shares  = 0.0
            trades.append({"action": "SELL", "price": current, "day": i})

        current_equity = capital + shares * actual_next
        equity.append(current_equity)

    # Close any open position
    if shares > 0:
        capital = shares * float(actuals[-1])
        shares  = 0.0

    final_equity = capital
    total_return = (final_equity - 100_000) / 100_000 * 100
    n_trades     = len(trades)
    wins         = sum(
        1 for j in range(1, len(trades))
        if trades[j]["action"] == "SELL"
        and trades[j]["price"] > trades[j-1]["price"]
    )

    return {
        "initial_capital_KES":  100_000,
        "final_capital_KES":    round(final_equity, 2),
        "total_return_pct":     round(total_return, 2),
        "n_trades":             n_trades,
        "win_rate_pct":         round(wins / max(n_trades // 2, 1) * 100, 1),
        "max_equity_KES":       round(float(np.max(equity)), 2),
        "min_equity_KES":       round(float(np.min(equity)), 2),
    }
