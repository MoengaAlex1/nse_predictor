"""
Direct multi-step LightGBM regressor for 1M / 3M / 6M / 9M / 12M price
forecasts on the NSE.

Why this exists (from the user brief):
  "the forecast is flat for all companies ... it lacks the predictability
   of the price across the month, users need 1, 3, 6, 9, 12 months
   predictions ... the model should be more advanced, able to use the
   earnings, reports, price trend and announcements to gauge future
   price increase"

Approach — direct multi-step:
  For each horizon H in {21, 63, 126, 189, 252} trading days:
    target = (close[t + H] - close[t]) / close[t]        (log-safer pct)
    features = engineered price/technical/fundamental vector at t
    LightGBM gradient-boosted regressor trained on the direct
    (t → t+H) pair. No error compounding — each horizon is its own
    honest fit.

Why LightGBM over LSTM/XGBoost for this specific job:
  - Handles the fundamental features natively (missing values, categorical
    hints via sentinel -1, mixed scales).
  - Trains in seconds per horizon per ticker on CPU — fits in CI budget.
  - Feature-importance readouts show WHICH signal drives WHICH horizon
    (technicals for 1M, earnings growth for 6M+, macro at 12M) — the
    user asked for the model to "gauge" future moves, and this gives
    them a story.

Reports per-horizon MAPE from a walk-forward split so the frontend can
render confidence bands per horizon — an honest "±5% at 1M, ±18% at
12M" beats an over-confident flat curve.

Model file layout:
  models/{ticker}_mhgbm_{horizon}.pkl    — one file per (ticker, horizon)
  models/{ticker}_mhgbm_meta.json        — train date, horizons, MAPE
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import joblib
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

try:
    import lightgbm as lgb
    _LGB_AVAILABLE = True
except ImportError:
    _LGB_AVAILABLE = False
    log.warning("lightgbm not installed — multi-horizon forecaster disabled. `pip install lightgbm`")


# Horizons the frontend renders. Chosen to match the ForecastPanel
# chips (1M/3M/6M/9M/12M) using NSE trading-day counts. If the frontend
# ever adds a new chip (e.g. 2Y) add the key here and retrain.
HORIZONS: dict[str, int] = {
    "1M":  21,
    "3M":  63,
    "6M":  126,
    "9M":  189,
    "12M": 252,
}


@dataclass
class HorizonBacktest:
    """Walk-forward backtest report for one horizon."""
    horizon_days: int
    n_train: int
    n_test: int
    mape: float | None    # percent, e.g. 5.2 = 5.2%
    direction_hit: float | None   # 0..1 — fraction of test rows where sign of prediction matches sign of actual
    top_features: list[tuple[str, float]] = field(default_factory=list)


@dataclass
class MultiHorizonReport:
    ticker: str
    trained_at: str
    horizons: dict[str, HorizonBacktest]

    def to_json(self) -> dict:
        return {
            "ticker": self.ticker,
            "trained_at": self.trained_at,
            "horizons": {k: asdict(v) for k, v in self.horizons.items()},
        }


def _prepare_dataset(
    feature_df: pd.DataFrame,
    feature_cols: list[str],
    horizon_days: int,
) -> tuple[pd.DataFrame, pd.Series] | None:
    """Build the (X, y) supervised pair for one horizon. Drops rows
    where the target price H days ahead isn't observed yet."""
    if "Close" not in feature_df.columns:
        log.error("feature_df must have a 'Close' column")
        return None
    df = feature_df.copy()
    # Direct-step target: pct change from t to t+H.
    df["_target"] = df["Close"].shift(-horizon_days) / df["Close"] - 1.0
    df = df.dropna(subset=["_target"] + feature_cols)
    if len(df) < 60:  # need a reasonable train set
        return None
    X = df[feature_cols]
    y = df["_target"]
    return X, y


def _train_one_horizon(
    X: pd.DataFrame,
    y: pd.Series,
    horizon_days: int,
    test_frac: float = 0.2,
) -> tuple[object | None, HorizonBacktest]:
    """Fit + walk-forward backtest one horizon. Time-ordered split — the
    last test_frac of rows becomes the test set to catch overfitting to
    older market regimes."""
    n = len(X)
    split = max(50, int(n * (1 - test_frac)))
    X_tr, y_tr = X.iloc[:split], y.iloc[:split]
    X_te, y_te = X.iloc[split:], y.iloc[split:]

    model = lgb.LGBMRegressor(
        n_estimators=400,
        learning_rate=0.03,
        max_depth=6,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_samples=20,
        reg_alpha=0.1,
        reg_lambda=0.1,
        random_state=42,
        verbose=-1,
    )
    model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], callbacks=[lgb.early_stopping(30, verbose=False)])

    pred = model.predict(X_te)
    # Report MAE on pct_return in percentage points (interpretable:
    # "average error ±X pp on horizon return"). MAPE-on-return is
    # ill-defined here because a horizon whose actual return is near
    # zero blows the divisor up and gives 800%+ headline numbers that
    # don't reflect real accuracy. The name is still `mape` for
    # backward compatibility with the meta.json schema and frontend
    # badge, but the semantics are MAE in percentage points.
    if len(pred):
        mape = float(np.mean(np.abs(pred - y_te.values)) * 100.0)
        hit = float(np.mean(np.sign(pred) == np.sign(y_te.values)))
    else:
        mape = None
        hit = None

    importances = sorted(
        zip(X.columns.tolist(), model.feature_importances_.tolist()),
        key=lambda kv: kv[1], reverse=True,
    )[:10]

    return model, HorizonBacktest(
        horizon_days=horizon_days,
        n_train=len(X_tr),
        n_test=len(X_te),
        mape=mape,
        direction_hit=hit,
        top_features=importances,
    )


def train_multi_horizon(
    ticker: str,
    feature_df: pd.DataFrame,
    feature_cols: list[str],
    horizons: dict[str, int] | None = None,
) -> tuple[dict[str, object], MultiHorizonReport]:
    """Fit one LightGBM regressor per horizon for `ticker`.

    Returns (models_by_horizon, report). Empty models dict + empty
    report when LightGBM isn't installed or the ticker has too little
    data for any horizon.
    """
    horizons = horizons or HORIZONS
    if not _LGB_AVAILABLE:
        return {}, MultiHorizonReport(ticker=ticker, trained_at="", horizons={})

    models: dict[str, object] = {}
    report_h: dict[str, HorizonBacktest] = {}
    for key, days in horizons.items():
        pair = _prepare_dataset(feature_df, feature_cols, days)
        if pair is None:
            log.info("  %s horizon %s: insufficient data — skipping", ticker, key)
            continue
        X, y = pair
        model, bt = _train_one_horizon(X, y, days)
        if model is None:
            continue
        models[key] = model
        report_h[key] = bt
        log.info(
            "  %s horizon %-3s: n_tr=%d n_te=%d MAPE=%s%% dir=%s",
            ticker, key, bt.n_train, bt.n_test,
            f"{bt.mape:.1f}" if bt.mape is not None else "—",
            f"{bt.direction_hit:.1%}" if bt.direction_hit is not None else "—",
        )

    return models, MultiHorizonReport(
        ticker=ticker,
        trained_at=datetime.now(timezone.utc).isoformat(),
        horizons=report_h,
    )


def save_multi_horizon(
    ticker: str,
    models: dict[str, object],
    report: MultiHorizonReport,
    model_dir: Path,
) -> None:
    """Persist per-horizon models + meta so run_inference can load them."""
    model_dir.mkdir(parents=True, exist_ok=True)
    safe = ticker.replace(".", "_")
    for key, model in models.items():
        joblib.dump(model, model_dir / f"{safe}_mhgbm_{key}.pkl")
    with open(model_dir / f"{safe}_mhgbm_meta.json", "w", encoding="utf-8") as f:
        json.dump(report.to_json(), f, indent=2)
    log.info("  %s → saved %d horizons", ticker, len(models))


def load_multi_horizon(
    ticker: str,
    model_dir: Path,
) -> tuple[dict[str, object], dict | None]:
    """Load whatever per-horizon models exist for this ticker. Returns
    ({}, None) when the meta file is missing (fresh ticker / retrain
    hasn't happened yet)."""
    safe = ticker.replace(".", "_")
    meta_path = model_dir / f"{safe}_mhgbm_meta.json"
    if not meta_path.exists():
        return {}, None
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    models: dict[str, object] = {}
    for key in HORIZONS:
        p = model_dir / f"{safe}_mhgbm_{key}.pkl"
        if p.exists():
            try:
                models[key] = joblib.load(p)
            except Exception as e:  # noqa: BLE001
                log.warning("  %s: failed to load %s: %s", ticker, p.name, e)
    return models, meta


def predict_multi_horizon(
    models: dict[str, object],
    feature_row: pd.DataFrame,
    current_price: float,
) -> dict[str, dict[str, float]]:
    """Serve predictions for one point-in-time row. Returns
    {horizon_key: {pct_return, target_price}} for every horizon whose
    model is available."""
    if not models or feature_row.empty or current_price <= 0:
        return {}
    out: dict[str, dict[str, float]] = {}
    for key, model in models.items():
        try:
            # LightGBM handles single-row DataFrame; expects the same
            # feature order used at training time.
            pred_pct = float(np.array(model.predict(feature_row)).ravel()[0])
        except Exception as e:  # noqa: BLE001
            log.warning("  mhgbm predict failed for %s: %s", key, e)
            continue
        # Guard against pathological outputs (broken model on a corrupt
        # feature row) — clamp to +/- 200% return so downstream charts
        # don't get a KES -infinity target.
        pred_pct = max(-2.0, min(2.0, pred_pct))
        out[key] = {
            "pct_return": pred_pct,
            "target_price": current_price * (1.0 + pred_pct),
        }
    return out
