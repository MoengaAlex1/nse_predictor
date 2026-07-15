"""
NSE Stock Prediction CLI

Usage:
    # NSE Nairobi stock (CSV required — yfinance does not carry .NR tickers)
    python main.py --ticker SCOM.NR --csv data/raw/safaricom.csv --investment 100000

    # Any yfinance-supported ticker (for testing)
    python main.py --ticker AAPL --investment 100000
    python main.py --ticker EQTY.NR --csv data/raw/equity.csv --investment 50000
"""
import argparse
import sys
import io
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Force UTF-8 stdout on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv, validate_ticker
from src.analysis.price_trend import price_change_analysis
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.analysis.risk import value_at_risk
from src.features.engineer import build_feature_matrix, select_top_features
from src.models.arima_model import train_arima, arima_forecast
from src.models.lstm_model import train_lstm, lstm_predict
from src.models.xgboost_model import train_xgboost
from src.models.ensemble import ensemble_predict, generate_signal, compute_ensemble_metrics
from src.visualization.dashboard import build_dashboard
from src.analysis.correlation import correlation_analysis
from config import START_DATE, DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE, DATA_CLEANED, DATA_FEATURES, NSE_TICKERS


def _build_corr_matrix() -> "pd.DataFrame | None":
    dfs = {}
    for t in NSE_TICKERS:
        path = DATA_CLEANED / f"{t.replace('.', '_')}_cleaned.csv"
        if path.exists():
            dfs[t] = pd.read_csv(path, index_col="Date", parse_dates=True)
    if len(dfs) < 2:
        return None
    return correlation_analysis(dfs)


def run(ticker: str, investment: float, start: str, csv_path: str = None):
    ticker = ticker.upper()
    if not ticker.endswith(".NR"):
        ticker += ".NR"

    print(f"\n{'='*60}")
    print(f"  NSE Stock Prediction System — {ticker}")
    print(f"{'='*60}\n")

    # ── 1. Data acquisition & cleaning ────────────────────────────────────
    print("[ 1/6 ] Fetching data...")
    raw_df = fetch_nse_data(ticker, start=start, csv_path=csv_path)

    print("[ 2/6 ] Cleaning data...")
    cleaned_df, report = clean_ohlcv(raw_df, ticker=ticker)
    valid = validate_ticker(cleaned_df, report)
    if not valid:
        print(f"\n⚠ {ticker} failed data quality checks. Results may be unreliable.")

    # ── 2. Core analysis ──────────────────────────────────────────────────
    print("\n[ 3/6 ] Running analysis...")
    trend   = price_change_analysis(cleaned_df)
    ret_df, ret_summary = daily_return_analysis(cleaned_df)
    ma_df   = compute_moving_averages(ret_df)
    var_res = value_at_risk(cleaned_df, investment=investment, confidence=DEFAULT_CONFIDENCE)

    print("\n── Price Trend ──────────────────────────────────────────")
    for k, v in trend.items():
        print(f"  {k}: {v}")

    print("\n── Returns Summary ──────────────────────────────────────")
    for k, v in ret_summary.items():
        print(f"  {k}: {v}")

    print("\n── Value at Risk ────────────────────────────────────────")
    for k, v in var_res.items():
        print(f"  {k}: {v}")

    # ── 3. Feature engineering ────────────────────────────────────────────
    print("\n[ 4/6 ] Engineering features...")
    feature_df = build_feature_matrix(ma_df)
    feature_cols = select_top_features(feature_df)

    # ── 4. Model training ─────────────────────────────────────────────────
    print("\n[ 5/6 ] Training models (this may take a few minutes)...")

    # ARIMA
    print("\n→ ARIMA")
    arima_preds, arima_actuals = _run_arima(cleaned_df)

    # LSTM
    print("\n→ LSTM (PyTorch)")
    lstm_preds, lstm_actuals, n_price_features = _run_lstm(feature_df, feature_cols, ticker)

    # XGBoost
    print("\n→ XGBoost")
    from src.models.xgboost_model import save_xgboost
    xgb_model, _, xgb_actuals, xgb_preds = train_xgboost(feature_df, feature_cols)
    save_xgboost(xgb_model, ticker)

    # Align lengths for ensemble
    n = min(len(lstm_preds), len(xgb_preds), len(arima_preds))
    ens_preds = ensemble_predict(
        lstm_preds[-n:], xgb_preds[-n:], arima_preds[-n:]
    )
    ens_metrics = compute_ensemble_metrics(lstm_actuals[-n:], ens_preds)

    # ── 5. Generate signal ────────────────────────────────────────────────
    current_price  = float(cleaned_df["Close"].iloc[-1])
    predicted_next = float(ens_preds[-1]) if len(ens_preds) > 0 else current_price
    var_pct        = var_res["historical_var_pct"]
    signal_result  = generate_signal(current_price, predicted_next, var_pct)

    # ── 6. Dashboard ──────────────────────────────────────────────────────
    print("\n[ 6/6 ] Generating dashboard...")
    corr_matrix = _build_corr_matrix()
    html_path = build_dashboard(
        df=ma_df,
        ticker=ticker,
        corr_matrix=corr_matrix,
        actual=lstm_actuals[-n:],
        predicted=ens_preds,
        investment=investment,
    )

    # ── Final output ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  SIGNAL REPORT — {ticker}")
    print(f"{'='*60}")
    print(f"  Signal:               {signal_result['signal']}")
    print(f"  Risk-Adjusted Signal: {signal_result['risk_adjusted_signal']}")
    print(f"  Current Price (KES):  {signal_result['current_price_KES']}")
    print(f"  Predicted Next (KES): {signal_result['predicted_price_KES']}")
    print(f"  Predicted Change:     {signal_result['predicted_change_pct']}%")
    print(f"  Historical VaR 95%:   {var_pct}%")
    print(f"  Rationale:            {signal_result['rationale']}")
    print(f"\n  Ensemble Metrics:")
    for k, v in ens_metrics.items():
        print(f"    {k}: {v}")
    print(f"\n  Dashboard saved: {html_path}")
    print(f"{'='*60}\n")

    # ── Save signal JSON for the web app ────────────────────────────────────
    _save_signal(ticker, {
        **signal_result,
        "metrics": ens_metrics,
        "actuals": lstm_actuals[-n:].tolist(),
        "preds":   ens_preds.tolist(),
    })

    return signal_result


def _save_signal(ticker: str, data: dict) -> None:
    import json
    DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    path = DATA_FEATURES / f"{ticker.replace('.', '_')}_signal.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _run_arima(df: pd.DataFrame):
    from src.models.arima_model import arima_predict_test
    import pandas as pd
    preds, actuals = arima_predict_test(df["Close"])
    from src.models.xgboost_model import evaluate
    evaluate(actuals, preds, label="ARIMA")
    return preds, actuals


def _run_lstm(feature_df, feature_cols, ticker: str):
    from src.models.lstm_model import save_lstm
    model, scaler, test_ds, device = train_lstm(feature_df, feature_cols)
    n_price_features = 1 + len(feature_cols)
    preds, actuals = lstm_predict(model, test_ds, scaler, device, n_price_features)
    save_lstm(model, scaler, ticker)
    from src.models.xgboost_model import evaluate
    evaluate(actuals, preds, label="LSTM")
    return preds, actuals, n_price_features


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSE Stock Prediction System")
    parser.add_argument("--ticker",     default="SCOM.NR", help="NSE ticker, e.g. SCOM.NR")
    parser.add_argument("--investment", type=float, default=DEFAULT_INVESTMENT,
                        help="Investment size in KES (default: 100000)")
    parser.add_argument("--start",      default=START_DATE,
                        help=f"Start date for historical data (default: {START_DATE})")
    parser.add_argument("--csv",        default=None,
                        help="Path to historical data CSV (required for NSE .NR tickers)")
    args = parser.parse_args()
    run(ticker=args.ticker, investment=args.investment, start=args.start, csv_path=args.csv)
