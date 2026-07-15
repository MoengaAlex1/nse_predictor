# pipeline/scripts/run_training.py
"""
Weekly training entry point — trains LSTM, XGBoost, ARIMA for all companies
and uploads model artifacts to Firebase Storage.

Usage: python pipeline/scripts/run_training.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import os
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
from src.features.engineer import build_feature_matrix, select_top_features
from src.models.lstm_model import train_lstm, save_lstm, lstm_predict
from src.models.xgboost_model import train_xgboost, save_xgboost
from src.models.arima_model import arima_predict_test
from src.models.ensemble import ensemble_predict, compute_ensemble_metrics
from scripts.push_to_firestore import get_db, upload_model_to_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()


def train_company(company: dict, db: Any) -> dict | None:
    ticker = company["ticker"]
    safe   = ticker.replace(".", "_")
    csv_p  = PIPELINE_ROOT / "data" / "raw" / company["csv"]
    log.info("Training %s ...", ticker)

    try:
        raw_df = fetch_nse_data(ticker, csv_path=str(csv_p) if csv_p.exists() else None)
        cleaned_df, _ = clean_ohlcv(raw_df, ticker=ticker)
        ret_df, _    = daily_return_analysis(cleaned_df)
        ma_df        = compute_moving_averages(ret_df)
        feature_df   = build_feature_matrix(ma_df)
        feature_cols = select_top_features(feature_df)

        model, scaler, test_ds, device = train_lstm(feature_df, feature_cols)
        save_lstm(model, scaler, ticker)
        n_price = 1 + len(feature_cols)
        lstm_preds, lstm_actuals = lstm_predict(model, test_ds, scaler, device, n_price)

        xgb_model, _, xgb_actuals, xgb_preds = train_xgboost(feature_df, feature_cols)
        save_xgboost(xgb_model, ticker)

        arima_preds, arima_actuals = arima_predict_test(cleaned_df["Close"])

        for fname in [f"{safe}_lstm.pt", f"{safe}_lstm_scaler.pkl", f"{safe}_xgboost.pkl"]:
            local_path = MODELS_DIR / fname
            if local_path.exists():
                upload_model_to_storage(str(local_path), f"models/{fname}")
                log.info("Uploaded %s", fname)

        n = min(len(lstm_preds), len(xgb_preds), len(arima_preds))
        ens = ensemble_predict(lstm_preds[-n:], xgb_preds[-n:], arima_preds[-n:])
        metrics = compute_ensemble_metrics(lstm_actuals[-n:], ens)

        (db.collection("companies")
           .document(safe)
           .collection("training_runs")
           .document(TODAY)
           .set({"date": TODAY, "metrics": metrics, "status": "ok"}))

        log.info("Done %s — MAPE=%.2f%%", ticker, metrics.get("mape", -1))
        return {"ticker": safe, "metrics": metrics}

    except Exception as e:
        log.error("FAILED %s: %s", ticker, e, exc_info=True)
        return None


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    db        = get_db()
    companies = load_companies()
    ok = 0
    failed = 0

    for company in companies:
        result = train_company(company, db)
        if result:
            ok += 1
        else:
            failed += 1

    log.info("Training complete: %d ok, %d failed", ok, failed)


if __name__ == "__main__":
    main()
