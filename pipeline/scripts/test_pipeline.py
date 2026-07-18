"""Quick functional smoke-test for the ML pipeline. Run from repo root."""
import sys
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
REPO = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO / "pipeline"))
sys.path.insert(0, str(REPO))

import numpy as np
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.features.engineer import build_feature_matrix, select_top_features, save_feature_cols, load_feature_cols
from src.models.arima_model import train_arima, arima_forecast, arima_forecast_with_ci, arima_predict_test
from src.models.xgboost_model import train_xgboost, save_xgboost, load_xgboost
from src.models.lstm_model import (
    train_lstm, save_lstm, load_lstm,
    lstm_predict, lstm_predict_next, lstm_forecast_30d,
)
from src.models.ensemble import ensemble_predict, generate_signal, compute_ensemble_metrics
from src.models.backtest import walk_forward_backtest, signal_backtest
from config import MODELS_DIR

TICKER = "SCOM.NR"
CSV_P = REPO / "data" / "cleaned" / "safaricom_cleaned.csv"


def test_data():
    print("\n[1] Data pipeline...")
    raw_df = fetch_nse_data(TICKER, csv_path=str(CSV_P) if CSV_P.exists() else None)
    cleaned_df, report = clean_ohlcv(raw_df, ticker=TICKER)
    print(f"    Rows: {len(cleaned_df)}  Close range: {cleaned_df['Close'].min():.2f} – {cleaned_df['Close'].max():.2f}")
    assert len(cleaned_df) > 500, "Need > 500 rows"
    return cleaned_df


def test_features(cleaned_df):
    print("\n[2] Feature engineering...")
    ret_df, _ = daily_return_analysis(cleaned_df)
    ma_df = compute_moving_averages(ret_df)
    feature_df = build_feature_matrix(ma_df)
    feature_cols = select_top_features(feature_df, n_features=15)  # 15 for speed
    print(f"    Rows: {len(feature_df)}  Selected features: {len(feature_cols)}")
    assert len(feature_cols) == 15
    return feature_df, feature_cols


def test_arima(cleaned_df):
    print("\n[3] ARIMA...")
    arima_fit = train_arima(cleaned_df["Close"])
    forecast = arima_forecast(arima_fit, steps=30).tolist()
    ci_df = arima_forecast_with_ci(arima_fit, steps=30)
    print(f"    30-day: {forecast[0]:.2f} → {forecast[-1]:.2f} KES")
    print(f"    CI at day 30: [{ci_df['lower_ci'].iloc[-1]:.2f}, {ci_df['upper_ci'].iloc[-1]:.2f}]")
    assert len(forecast) == 30
    return arima_fit, forecast


def test_xgboost(feature_df, feature_cols):
    print("\n[4] XGBoost...")
    xgb_model, X_test, y_test, y_pred = train_xgboost(feature_df, feature_cols)
    next_price = float(xgb_model.predict(feature_df[feature_cols].iloc[[-1]])[0])
    print(f"    Next-day: {next_price:.2f} KES  (test RMSE already logged above)")
    assert next_price > 0
    return xgb_model, y_test, y_pred


def test_lstm(feature_df, feature_cols):
    print("\n[5] LSTM (reduced epochs for smoke-test)...")
    model, scaler, test_ds, device = train_lstm(
        feature_df, feature_cols, epochs=5, patience=3
    )
    preds, actuals = lstm_predict(model, test_ds, scaler, device, 1 + len(feature_cols))
    next_price = lstm_predict_next(model, feature_df, feature_cols, scaler, device)
    forecast_30 = lstm_forecast_30d(model, feature_df, feature_cols, scaler, device, steps=30)
    print(f"    Test preds: {len(preds)}  Next-day: {next_price:.2f} KES")
    print(f"    30-day range: {min(forecast_30):.2f} – {max(forecast_30):.2f} KES")
    assert len(forecast_30) == 30
    assert next_price > 0
    return model, scaler, preds, actuals


def test_save_load(model, scaler, feature_cols):
    print("\n[6] Save / Load cycle...")
    tmp_dir = MODELS_DIR
    save_lstm(model, scaler, TICKER, model_dir=tmp_dir)
    save_feature_cols(feature_cols, TICKER, model_dir=tmp_dir)
    loaded_cols = load_feature_cols(TICKER, model_dir=tmp_dir)
    assert loaded_cols == feature_cols, "Feature cols round-trip failed"
    loaded_model, loaded_scaler = load_lstm(TICKER, 1 + len(feature_cols), model_dir=tmp_dir)
    print("    Save/load: OK")
    return loaded_model, loaded_scaler


def test_ensemble(feature_df, feature_cols, xgb_model, xgb_y_test, xgb_preds, lstm_preds, lstm_actuals, arima_forecast_vals):
    print("\n[7] Ensemble + Signal...")
    n = min(len(lstm_preds), len(xgb_preds), len(arima_forecast_vals))
    ens = ensemble_predict(lstm_preds[-n:], xgb_preds[-n:], np.array(arima_forecast_vals[:n]))
    metrics = compute_ensemble_metrics(lstm_actuals[-n:], ens)
    print(f"    RMSE={metrics['rmse']:.4f}  MAPE={metrics['mape']:.2f}%  DirAcc={metrics['directional_accuracy']:.1f}%")

    current = float(feature_df["Close"].iloc[-1])
    sig = generate_signal(current, float(ens[-1]), var_pct=-1.5)
    print(f"    Signal: {sig['signal']} ({sig['predicted_change_pct']:.2f}%)")


def test_backtest(feature_df, cleaned_df, feature_cols, xgb_preds):
    print("\n[8] Backtest...")
    bt = walk_forward_backtest(feature_df, cleaned_df, feature_cols, n_splits=3)
    if "error" not in bt:
        print(f"    WF avg_mape={bt['avg_mape']}%  avg_dir_acc={bt['avg_directional_accuracy']}%")
    else:
        print(f"    WF error: {bt['error']}")
    sb = signal_backtest(cleaned_df["Close"], xgb_preds)
    if "error" not in sb:
        print(f"    Signal PnL: {sb['total_return_pct']}%  trades={sb['n_trades']}")


def main():
    print("=== NSE ML Pipeline Smoke Test ===")
    cleaned_df = test_data()
    feature_df, feature_cols = test_features(cleaned_df)
    arima_fit, arima_30d = test_arima(cleaned_df)
    xgb_model, xgb_actuals, xgb_preds = test_xgboost(feature_df, feature_cols)
    lstm_model, scaler, lstm_preds, lstm_actuals = test_lstm(feature_df, feature_cols)
    test_save_load(lstm_model, scaler, feature_cols)
    test_ensemble(feature_df, feature_cols, xgb_model, xgb_actuals, xgb_preds, lstm_preds, lstm_actuals, arima_30d)
    test_backtest(feature_df, cleaned_df, feature_cols, xgb_preds)
    print("\n=== ALL TESTS PASSED ===\n")


if __name__ == "__main__":
    main()
