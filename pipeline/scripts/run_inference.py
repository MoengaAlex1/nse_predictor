# pipeline/scripts/run_inference.py
"""
Daily inference entry point.

Key design decisions:
- Loads pre-trained models from Firebase Storage (never retrains LSTM/XGBoost).
- Fallback: if no saved model exists (first run), trains reduced-epoch models.
- Uses LSTM for true next-day forward prediction (not test-set evaluation).
- Uses ARIMA's native multi-step forecast for the 30-day price trajectory.
- Runs up to 4 companies concurrently via ThreadPoolExecutor.

Usage: python pipeline/scripts/run_inference.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import os
import json
import logging
import tempfile as _tempfile
from pathlib import Path
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import torch
import joblib

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import (
    load_companies, MODELS_DIR,
    DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE,
    ENSEMBLE_WEIGHTS, SEQUENCE_LENGTH,
)
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.analysis.risk import value_at_risk
from src.features.engineer import (
    build_feature_matrix, select_top_features,
    save_feature_cols, load_feature_cols,
)
from src.models.lstm_model import (
    NSELSTMModel, train_lstm, save_lstm,
    lstm_predict, lstm_predict_next, lstm_forecast_30d,
)
from src.models.xgboost_model import train_xgboost, save_xgboost, load_xgboost
from src.models.arima_model import (
    train_arima, arima_forecast, arima_predict_test, save_arima, load_arima,
)
from src.models.ensemble import ensemble_predict, generate_signal, compute_ensemble_metrics
from scripts.push_to_firestore import (
    get_db, write_snapshot, write_technicals,
    update_company_public, write_market_overview,
    download_model_from_storage, prune_old_docs,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()
MODELS_TMP = Path(_tempfile.gettempdir()) / "nse_models"


def _next_trading_day(from_date: date | None = None) -> date:
    """First NSE trading day (Mon-Fri) strictly after from_date."""
    d = (from_date or date.today()) + timedelta(days=1)
    while d.weekday() >= 5:          # 5=Saturday, 6=Sunday
        d += timedelta(days=1)
    return d


def _forecast_trading_dates(base: date, n: int) -> list[str]:
    """n consecutive trading-day ISO dates starting the day after base."""
    dates: list[str] = []
    d = base
    while len(dates) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            dates.append(d.isoformat())
    return dates

# Artifact filenames (must match run_training.py)
_ARTIFACT_SUFFIXES = [
    "_lstm.pt",
    "_lstm_scaler.pkl",
    "_xgboost.pkl",
    "_arima.pkl",
    "_feature_cols.json",
]
_CORE_SUFFIXES = [
    "_lstm.pt",
    "_lstm_scaler.pkl",
    "_xgboost.pkl",
    "_arima.pkl",
]


# ── Model helpers ─────────────────────────────────────────────────────────────

def _download_models(safe: str) -> bool:
    """Download all 5 artifacts from Firebase Storage into MODELS_TMP. Returns True if all found."""
    all_ok = True
    for suffix in _ARTIFACT_SUFFIXES:
        fname = f"{safe}{suffix}"
        ok = download_model_from_storage(
            storage_path=f"models/{fname}",
            local_path=str(MODELS_TMP / fname),
        )
        if not ok:
            log.warning("Not found in Storage: %s", fname)
            all_ok = False
    return all_ok


def _models_cached(safe: str) -> bool:
    return all((MODELS_TMP / f"{safe}{s}").exists() for s in _ARTIFACT_SUFFIXES)


def _core_models_cached(safe: str) -> bool:
    """True when LSTM/XGBoost/ARIMA artifacts exist but feature_cols.json may be absent."""
    return all((MODELS_TMP / f"{safe}{s}").exists() for s in _CORE_SUFFIXES)


def _load_or_train_models(
    ticker: str,
    safe: str,
    feature_df: pd.DataFrame,
    feature_cols: list,
    cleaned_df: pd.DataFrame,
) -> tuple:
    """
    Returns (lstm_model, scaler, xgb_model, arima_fitted, feature_cols, device).
    Attempts to load from MODELS_TMP; falls back to training if artifacts are missing.
    """
    device = torch.device("cpu")

    if _models_cached(safe):
        log.info("  Loading saved models for %s", ticker)
        try:
            with open(MODELS_TMP / f"{safe}_feature_cols.json") as f:
                feature_cols = json.load(f)

            n_features = 1 + len(feature_cols)
            lstm_model = NSELSTMModel(n_features)
            state = torch.load(
                MODELS_TMP / f"{safe}_lstm.pt",
                map_location="cpu",
                weights_only=True,
            )
            lstm_model.load_state_dict(state)
            lstm_model.eval()

            scaler    = joblib.load(MODELS_TMP / f"{safe}_lstm_scaler.pkl")
            xgb_model = joblib.load(MODELS_TMP / f"{safe}_xgboost.pkl")
            arima_fit = joblib.load(MODELS_TMP / f"{safe}_arima.pkl")

            return lstm_model, scaler, xgb_model, arima_fit, feature_cols, device

        except Exception as e:
            log.warning("  Failed to load saved models for %s (%s) — retraining", ticker, e)

    elif _core_models_cached(safe):
        # feature_cols.json missing (models trained before v2 feature persistence).
        # Recover feature list from XGBoost's stored feature names — no retraining needed.
        log.info("  Core models present, feature_cols.json missing for %s — recovering", ticker)
        try:
            xgb_model = joblib.load(MODELS_TMP / f"{safe}_xgboost.pkl")
            feature_cols = list(xgb_model.feature_names_in_)
            save_feature_cols(feature_cols, ticker, model_dir=MODELS_TMP)
            log.info("  Recovered %d feature cols for %s from XGBoost", len(feature_cols), ticker)

            n_features = 1 + len(feature_cols)
            lstm_model = NSELSTMModel(n_features)
            state = torch.load(
                MODELS_TMP / f"{safe}_lstm.pt",
                map_location="cpu",
                weights_only=True,
            )
            lstm_model.load_state_dict(state)
            lstm_model.eval()

            scaler    = joblib.load(MODELS_TMP / f"{safe}_lstm_scaler.pkl")
            arima_fit = joblib.load(MODELS_TMP / f"{safe}_arima.pkl")

            try:
                from scripts.push_to_firestore import upload_model_to_storage
                fname = f"{safe}_feature_cols.json"
                upload_model_to_storage(str(MODELS_TMP / fname), f"models/{fname}")
                log.info("  Uploaded recovered feature_cols.json for %s", ticker)
            except Exception as ue:
                log.warning("  Could not upload recovered feature_cols.json: %s", ue)

            return lstm_model, scaler, xgb_model, arima_fit, feature_cols, device

        except Exception as e:
            log.warning("  Feature recovery failed for %s (%s) — retraining", ticker, e)

    # ── Fallback: train from scratch (first run or all artifacts missing) ─────
    log.info("  No cached models for %s — training (first run or Storage empty)", ticker)
    lstm_model, scaler, _, _ = train_lstm(feature_df, feature_cols, epochs=50, patience=10)
    xgb_model, _, _, _       = train_xgboost(feature_df, feature_cols)
    arima_fit                 = train_arima(cleaned_df["Close"], order=(2, 1, 2))

    MODELS_TMP.mkdir(parents=True, exist_ok=True)
    save_lstm(lstm_model, scaler, ticker, model_dir=MODELS_TMP)
    save_xgboost(xgb_model, ticker, model_dir=MODELS_TMP)
    save_arima(arima_fit, ticker, model_dir=MODELS_TMP)
    save_feature_cols(feature_cols, ticker, model_dir=MODELS_TMP)

    try:
        from scripts.push_to_firestore import upload_model_to_storage
        for suffix in _ARTIFACT_SUFFIXES:
            fname = f"{safe}{suffix}"
            local = MODELS_TMP / fname
            if local.exists():
                upload_model_to_storage(str(local), f"models/{fname}")
    except Exception as e:
        log.warning("  Upload after fallback training failed: %s", e)

    return lstm_model, scaler, xgb_model, arima_fit, feature_cols, device


# ── Per-company pipeline ──────────────────────────────────────────────────────

def build_technicals_result(df: pd.DataFrame, date_str: str) -> dict:
    try:
        import ta
        close  = df["Close"]
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

        rsi    = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        macd_i = ta.trend.MACD(close)
        bb     = ta.volatility.BollingerBands(close)
        sma20  = close.rolling(20).mean().iloc[-1]
        sma50  = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        ema12  = close.ewm(span=12).mean().iloc[-1]
        ema26  = close.ewm(span=26).mean().iloc[-1]

        monthly = (df["Close"].resample("ME").last().pct_change() * 100).dropna()
        monthly_heatmap = {str(k)[:7]: round(float(v), 2) for k, v in monthly.items()}

        def _f(x):
            return None if (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)

        return {
            "date":           date_str,
            "rsi_14":         _f(rsi),
            "macd":           _f(macd_i.macd().iloc[-1]),
            "macd_signal":    _f(macd_i.macd_signal().iloc[-1]),
            "macd_hist":      _f(macd_i.macd_diff().iloc[-1]),
            "bb_upper":       _f(bb.bollinger_hband().iloc[-1]),
            "bb_mid":         _f(bb.bollinger_mavg().iloc[-1]),
            "bb_lower":       _f(bb.bollinger_lband().iloc[-1]),
            "sma_20":         _f(sma20),
            "sma_50":         _f(sma50),
            "sma_200":        _f(sma200),
            "ema_12":         _f(ema12),
            "ema_26":         _f(ema26),
            "volume":         int(volume.iloc[-1]) if len(volume) else 0,
            "avg_volume_30d": int(volume.tail(30).mean()) if len(volume) else 0,
            "daily_return":   _f(df["Close"].pct_change().iloc[-1] * 100),
            "volatility_30d": _f(df["Close"].pct_change().tail(30).std() * 100),
            "monthly_heatmap": monthly_heatmap,
        }
    except Exception as e:
        log.error("Technicals failed: %s", e)
        return {
            "date": date_str, "error": str(e),
            "rsi_14": None, "macd": None, "macd_signal": None, "macd_hist": None,
            "bb_upper": None, "bb_mid": None, "bb_lower": None,
            "sma_20": None, "sma_50": None, "sma_200": None,
            "ema_12": None, "ema_26": None,
            "volume": 0, "avg_volume_30d": 0,
            "daily_return": None, "volatility_30d": None, "monthly_heatmap": {},
        }


def run_company(company: dict, csv_override: Path | None = None) -> dict | None:
    ticker = company["ticker"]
    safe   = ticker.replace(".", "_")
    csv_p  = PIPELINE_ROOT.parent / "data" / "raw" / company["csv"]
    log.info("Processing %s ...", ticker)

    try:
        # ── 1. Data ──────────────────────────────────────────────────────────
        csv_local = CSVS_TMP / f"{safe}_cleaned.csv"
        if csv_override is not None and csv_override.exists():
            csv_path_arg = str(csv_override)
        elif csv_local.exists():
            csv_path_arg = str(csv_local)
        elif csv_p.exists():
            csv_path_arg = str(csv_p)
        else:
            csv_path_arg = None
        raw_df     = fetch_nse_data(ticker, csv_path=csv_path_arg)
        cleaned_df, _ = clean_ohlcv(raw_df, ticker=ticker)
        ret_df, _  = daily_return_analysis(cleaned_df)
        ma_df      = compute_moving_averages(ret_df)
        var_res    = value_at_risk(cleaned_df, investment=DEFAULT_INVESTMENT,
                                   confidence=DEFAULT_CONFIDENCE)
        feature_df = build_feature_matrix(ma_df)

        # Use placeholder feature_cols; _load_or_train_models will override from saved JSON
        placeholder_cols = select_top_features(feature_df) if not _models_cached(safe) else []

        # ── 2. Load (or train) models ─────────────────────────────────────────
        lstm_model, scaler, xgb_model, arima_fit, feature_cols, device = (
            _load_or_train_models(ticker, safe, feature_df, placeholder_cols, cleaned_df)
        )

        # Ensure feature_df contains all required columns
        missing = [c for c in feature_cols if c not in feature_df.columns]
        if missing:
            log.warning("%s: %d feature cols missing from current data, rebuilding features", ticker, len(missing))
            feature_df = build_feature_matrix(ma_df)

        # ── 3. Next-day predictions from each model ───────────────────────────
        # LSTM: true forward prediction on most recent SEQUENCE_LENGTH rows
        try:
            lstm_next = lstm_predict_next(lstm_model, feature_df, feature_cols, scaler, device)
        except Exception as e:
            log.warning("%s LSTM predict_next failed (%s) — using last Close", ticker, e)
            lstm_next = float(cleaned_df["Close"].iloc[-1])

        # XGBoost: predict on the last row of feature matrix
        last_row = feature_df[feature_cols].iloc[[-1]]
        xgb_next = float(xgb_model.predict(last_row)[0])

        # ARIMA: refit on latest Close and forecast 30 days
        # We refit because ARIMA state degrades without new data; it's fast (< 1s)
        try:
            arima_fit_latest = train_arima(cleaned_df["Close"], order=(2, 1, 2))
            arima_30d = arima_forecast(arima_fit_latest, steps=30).tolist()
        except Exception as e:
            log.warning("%s ARIMA refit failed (%s) — using loaded model", ticker, e)
            arima_30d = arima_forecast(arima_fit, steps=30).tolist()

        arima_next = arima_30d[0]

        # ── 4. Ensemble next-day prediction ───────────────────────────────────
        w_lstm, w_xgb, w_arima = ENSEMBLE_WEIGHTS
        predicted_next = w_lstm * lstm_next + w_xgb * xgb_next + w_arima * arima_next

        # ── 5. 30-day forecast for display ───────────────────────────────────
        # Use ARIMA for the trajectory (native multi-step); blend with LSTM rolling
        try:
            lstm_30d = lstm_forecast_30d(lstm_model, feature_df, feature_cols, scaler, device)
            forecast_30d = [
                round(w_lstm * l + w_arima * a + w_xgb * xgb_next, 4)
                for l, a in zip(lstm_30d, arima_30d)
            ]
        except Exception as e:
            log.warning("%s LSTM 30d forecast failed (%s) — using ARIMA only", ticker, e)
            forecast_30d = [round(float(v), 4) for v in arima_30d]

        # ── 6. Ensemble metrics on historical test set (diagnostic) ──────────
        try:
            from src.models.lstm_model import lstm_predict, SequenceDataset
            from src.data.cleaner import clean_ohlcv
            from sklearn.preprocessing import MinMaxScaler
            import math

            cols_for_eval = ["Close"] + feature_cols
            data_eval = feature_df[cols_for_eval].values.astype(float)
            split = int(len(data_eval) * 0.80)
            test_data = data_eval[split:]

            test_scaled = scaler.transform(test_data)
            test_ds = SequenceDataset(test_scaled)

            if len(test_ds) >= 2:
                lstm_preds_hist, lstm_act_hist = lstm_predict(
                    lstm_model, test_ds, scaler, device, 1 + len(feature_cols)
                )
                arima_preds_hist, arima_act_hist = arima_predict_test(cleaned_df["Close"])
                xgb_preds_hist = xgb_model.predict(feature_df[feature_cols].iloc[split:])
                xgb_act_hist   = feature_df["Close"].iloc[split:].values

                n = min(len(lstm_preds_hist), len(xgb_preds_hist), len(arima_preds_hist))
                ens_h = ensemble_predict(
                    lstm_preds_hist[-n:], xgb_preds_hist[-n:], arima_preds_hist[-n:]
                )
                ens_metrics = compute_ensemble_metrics(lstm_act_hist[-n:], ens_h)
                actuals_out = lstm_act_hist[-n:].tolist()
                preds_out   = ens_h.tolist()
            else:
                ens_metrics = {"rmse": None, "mae": None, "mape": None, "directional_accuracy": None}
                actuals_out = []
                preds_out   = []
        except Exception as e:
            log.warning("%s metrics eval failed: %s", ticker, e)
            ens_metrics = {"rmse": None, "mae": None, "mape": None, "directional_accuracy": None}
            actuals_out = []
            preds_out   = []

        # ── 7. Signal generation ──────────────────────────────────────────────
        current_price = float(cleaned_df["Close"].iloc[-1])
        var_pct       = var_res["historical_var_pct"]
        signal_result = generate_signal(current_price, predicted_next, var_pct)

        # ── 8. Build Firestore payloads ───────────────────────────────────────
        target_date = _next_trading_day(date.today())
        forecast_dates = _forecast_trading_dates(date.today(), len(forecast_30d))

        snapshot = {
            **signal_result,
            "run_date":          TODAY,
            "next_trading_day":  target_date.isoformat(),
            "forecast_dates":    forecast_dates,
            "metrics":           ens_metrics,
            "actuals":           actuals_out,
            "preds":             preds_out,
            "forecast":          forecast_30d,
            "lstm_next":         round(lstm_next, 4),
            "xgb_next":          round(xgb_next, 4),
            "arima_next":        round(arima_next, 4),
        }

        technicals = build_technicals_result(cleaned_df, TODAY)

        change_pct = float(cleaned_df["Close"].pct_change().iloc[-1] * 100)
        hist_90 = cleaned_df["Close"].tail(90)
        price_history = [
            {"date": str(idx.date()), "price": round(float(val), 4)}
            for idx, val in hist_90.items()
        ]

        return {
            "ticker": safe,
            "snapshot": snapshot,
            "technicals": technicals,
            "public_update": {
                "current_price":    round(current_price, 4),
                "change_pct_today": round(change_pct, 4),
                "signal":           signal_result["signal"],
                "price_history":    price_history,
                "price_preview":    [p["price"] for p in price_history[-30:]],
                "last_updated":     TODAY,
            },
        }

    except Exception as e:
        log.error("FAILED %s: %s", ticker, e, exc_info=True)
        return None


# ── Market overview aggregation ───────────────────────────────────────────────

def aggregate_market_overview(results: list[dict]) -> dict:
    rows: list[tuple[str, float]] = []
    signals: dict[str, int] = {"BUY": 0, "HOLD": 0, "SELL": 0}

    for r in results:
        if r is None:
            continue
        pub = r["public_update"]
        rows.append((r["ticker"], pub["change_pct_today"]))
        sig = pub["signal"]
        signals[sig] = signals.get(sig, 0) + 1

    rows.sort(key=lambda x: x[1], reverse=True)
    top_gainers = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[:5]]
    top_losers  = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[-5:]]

    return {
        "date":                TODAY,
        "top_gainers":         top_gainers,
        "top_losers":          top_losers,
        "signal_distribution": signals,
        "sector_performance":  {},
        "nse20_value":         None,
        "nse20_change_pct":    None,
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    MODELS_TMP.mkdir(parents=True, exist_ok=True)
    db        = get_db()
    companies = load_companies()

    ticker_filter = os.environ.get("NSE_TICKERS_FILTER", "").strip()
    if ticker_filter:
        allowed = {t.strip().upper() for t in ticker_filter.split(",") if t.strip()}
        companies = [c for c in companies if c["ticker"].upper() in allowed]
        log.info("NSE_TICKERS_FILTER active — running %d/%d companies: %s",
                 len(companies), len(load_companies()), ", ".join(allowed))

    results: list[dict] = []

    # Download latest cleaned CSVs from Firebase Storage
    CSVS_TMP = Path(_tempfile.gettempdir()) / "nse_csvs"
    CSVS_TMP.mkdir(parents=True, exist_ok=True)
    log.info("Downloading latest cleaned CSVs for %d companies...", len(companies))
    for company in companies:
        safe = company["ticker"].replace(".", "_")
        ok = download_model_from_storage(
            storage_path=f"data/cleaned/{safe}_cleaned.csv",
            local_path=str(CSVS_TMP / f"{safe}_cleaned.csv"),
        )
        if not ok:
            log.warning("No CSV in Storage for %s — will use repo fallback", safe)

    # Pre-download all model artifacts before parallel inference
    # (avoids concurrent Firebase Storage requests racing for the same files)
    log.info("Pre-downloading model artifacts for %d companies...", len(companies))
    for company in companies:
        safe = company["ticker"].replace(".", "_")
        if not _models_cached(safe):
            _download_models(safe)

    log.info("Starting inference with 4 parallel workers...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(
                run_company,
                c,
                CSVS_TMP / f"{c['ticker'].replace('.', '_')}_cleaned.csv",
            ): c
            for c in companies
        }
        for fut in as_completed(futures):
            res = fut.result()
            if res is None:
                continue
            write_snapshot(db, res["ticker"], TODAY, res["snapshot"])
            write_technicals(db, res["ticker"], TODAY, res["technicals"])
            update_company_public(db, res["ticker"], res["public_update"])
            ps = prune_old_docs(db, res["ticker"], "snapshots")
            pt = prune_old_docs(db, res["ticker"], "technicals")
            if ps or pt:
                log.info("  Pruned %d snapshot(s), %d technical(s) for %s", ps, pt, res["ticker"])
            results.append(res)
            log.info("Written to Firestore: %-20s signal=%s  price=%.2f",
                     res["ticker"],
                     res["public_update"]["signal"],
                     res["public_update"]["current_price"])

    overview = aggregate_market_overview(results)
    write_market_overview(db, TODAY, overview)
    log.info(
        "Done — %d/%d companies processed. Signals: BUY=%d HOLD=%d SELL=%d",
        len(results), len(companies),
        overview["signal_distribution"].get("BUY", 0),
        overview["signal_distribution"].get("HOLD", 0),
        overview["signal_distribution"].get("SELL", 0),
    )


if __name__ == "__main__":
    main()
