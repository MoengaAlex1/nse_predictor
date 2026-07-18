# pipeline/scripts/run_training.py
"""
Weekly training entry point.
Trains LSTM, XGBoost, ARIMA for all companies and uploads 5 artifacts per ticker:
  {safe}_lstm.pt, {safe}_lstm_scaler.pkl, {safe}_xgboost.pkl,
  {safe}_arima.pkl, {safe}_feature_cols.json

Usage: python pipeline/scripts/run_training.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import logging
from pathlib import Path
from datetime import date
from typing import Any

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies, MODELS_DIR
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.features.engineer import build_feature_matrix, select_top_features, save_feature_cols
from src.models.lstm_model import train_lstm, save_lstm, lstm_predict
from src.models.xgboost_model import train_xgboost, save_xgboost
from src.models.arima_model import train_arima, arima_predict_test, save_arima
from src.models.ensemble import ensemble_predict, compute_ensemble_metrics
from src.models.backtest import walk_forward_backtest, signal_backtest
from scripts.push_to_firestore import get_db, upload_model_to_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()

# Artifacts saved per ticker (must all be uploaded)
_ARTIFACT_SUFFIXES = [
    "_lstm.pt",
    "_lstm_scaler.pkl",
    "_xgboost.pkl",
    "_arima.pkl",
    "_feature_cols.json",
]


def _upload_artifacts(safe: str) -> None:
    for suffix in _ARTIFACT_SUFFIXES:
        fname = f"{safe}{suffix}"
        local = MODELS_DIR / fname
        if local.exists():
            upload_model_to_storage(str(local), f"models/{fname}")
            log.info("  Uploaded → models/%s", fname)
        else:
            log.warning("  Artifact missing, skipping upload: %s", fname)


def train_company(company: dict, db: Any) -> dict | None:
    ticker = company["ticker"]
    safe   = ticker.replace(".", "_")
    csv_p  = PIPELINE_ROOT / "data" / "raw" / company["csv"]
    log.info("Training %s ...", ticker)

    try:
        # ── 1. Data ──────────────────────────────────────────────────────────
        raw_df = fetch_nse_data(ticker, csv_path=str(csv_p) if csv_p.exists() else None)
        cleaned_df, _ = clean_ohlcv(raw_df, ticker=ticker)
        ret_df, _     = daily_return_analysis(cleaned_df)
        ma_df         = compute_moving_averages(ret_df)
        feature_df    = build_feature_matrix(ma_df)
        feature_cols  = select_top_features(feature_df)

        # ── 2. Persist feature list (MUST happen before model uploads) ────────
        save_feature_cols(feature_cols, ticker, model_dir=MODELS_DIR)

        # ── 3. LSTM ──────────────────────────────────────────────────────────
        lstm_model, scaler, test_ds, device = train_lstm(feature_df, feature_cols)
        save_lstm(lstm_model, scaler, ticker, model_dir=MODELS_DIR)
        n_total = 1 + len(feature_cols)
        lstm_preds, lstm_actuals = lstm_predict(lstm_model, test_ds, scaler, device, n_total)

        # ── 4. XGBoost ───────────────────────────────────────────────────────
        xgb_model, _, xgb_actuals, xgb_preds = train_xgboost(feature_df, feature_cols)
        save_xgboost(xgb_model, ticker, model_dir=MODELS_DIR)

        # ── 5. ARIMA (fit on full Close series for best long-horizon forecasts) ─
        arima_fitted = train_arima(cleaned_df["Close"], order=(2, 1, 2))
        save_arima(arima_fitted, ticker, model_dir=MODELS_DIR)

        # ── 6. Ensemble metrics on test set ──────────────────────────────────
        # Use ARIMA test-set predictions for metric alignment
        arima_preds, arima_actuals = arima_predict_test(cleaned_df["Close"])
        n = min(len(lstm_preds), len(xgb_preds), len(arima_preds))
        ens = ensemble_predict(lstm_preds[-n:], xgb_preds[-n:], arima_preds[-n:])
        metrics = compute_ensemble_metrics(lstm_actuals[-n:], ens)

        # ── 7. Walk-forward backtest (uses XGBoost for speed) ────────────────
        try:
            backtest_res = walk_forward_backtest(feature_df, cleaned_df, feature_cols, n_splits=5)
            sig_backtest = signal_backtest(cleaned_df["Close"], xgb_preds)
        except Exception as bt_err:
            log.warning("Backtest failed for %s: %s", ticker, bt_err)
            backtest_res = {}
            sig_backtest = {}

        # ── 8. Upload all 5 artifacts to Firebase Storage ────────────────────
        _upload_artifacts(safe)

        # ── 9. Record training run in Firestore ──────────────────────────────
        (db.collection("companies")
           .document(safe)
           .collection("training_runs")
           .document(TODAY)
           .set({
               "date":         TODAY,
               "metrics":      metrics,
               "backtest":     backtest_res,
               "signal_pnl":   sig_backtest,
               "status":       "ok",
               "n_features":   len(feature_cols),
               "feature_cols": feature_cols,
           }))

        log.info("Done %-20s MAPE=%.2f%%  DirAcc=%.1f%%",
                 ticker, metrics.get("mape", -1), metrics.get("directional_accuracy", -1))
        return {"ticker": safe, "metrics": metrics}

    except Exception as e:
        log.error("FAILED %s: %s", ticker, e, exc_info=True)
        try:
            (db.collection("companies")
               .document(safe)
               .collection("training_runs")
               .document(TODAY)
               .set({"date": TODAY, "status": "failed", "error": str(e)}))
        except Exception:
            pass
        return None


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    db        = get_db()
    companies = load_companies()
    ok = failed = 0

    for company in companies:
        result = train_company(company, db)
        if result:
            ok += 1
        else:
            failed += 1

    log.info("Training complete: %d ok, %d failed (total: %d)", ok, failed, ok + failed)


if __name__ == "__main__":
    main()
