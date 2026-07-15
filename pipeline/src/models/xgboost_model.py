import sys
import io
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error
import joblib
from pathlib import Path
from config import TRAIN_SPLIT, MODELS_DIR

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def train_xgboost(
    df: pd.DataFrame,
    feature_cols: list,
    target_col: str = "Close",
) -> tuple:
    X = df[feature_cols]
    y = df[target_col]

    split = int(len(df) * TRAIN_SPLIT)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    params = {
        "objective":            "reg:squarederror",
        "n_estimators":         1000,
        "learning_rate":        0.05,
        "max_depth":            6,
        "min_child_weight":     1,
        "subsample":            0.8,
        "colsample_bytree":     0.8,
        "reg_alpha":            0.1,
        "reg_lambda":           1.0,
        "random_state":         42,
        "n_jobs":               -1,
        "early_stopping_rounds": 50,  # XGBoost 3.x: set in constructor
    }

    model = xgb.XGBRegressor(**params)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=100,
    )

    y_pred = model.predict(X_test)
    _print_metrics(y_test.values, y_pred, label="XGBoost")
    return model, X_test, y_test.values, y_pred


def _print_metrics(y_true, y_pred, label: str = "Model") -> dict:
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae  = float(mean_absolute_error(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.where(y_true == 0, 1, y_true))) * 100)
    dir_acc = float(np.mean(np.sign(np.diff(y_true)) == np.sign(np.diff(y_pred))) * 100)
    print(f"\n[{label}] RMSE: {rmse:.4f} | MAE: {mae:.4f} | MAPE: {mape:.2f}% | Dir Acc: {dir_acc:.1f}%")
    return {"rmse": rmse, "mae": mae, "mape": mape, "directional_accuracy": dir_acc}


def evaluate(y_true: np.ndarray, y_pred: np.ndarray, label: str = "Model") -> dict:
    return _print_metrics(y_true, y_pred, label)


def save_xgboost(model, ticker: str) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = MODELS_DIR / f"{ticker.replace('.', '_')}_xgboost.pkl"
    joblib.dump(model, path)
    print(f"  XGBoost model saved -> {path.name}")
    return path


def load_xgboost(ticker: str):
    path = MODELS_DIR / f"{ticker.replace('.', '_')}_xgboost.pkl"
    return joblib.load(path)
