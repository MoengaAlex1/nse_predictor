# pipeline/scripts/run_inference.py
"""
Daily inference entry point.
Usage: python pipeline/scripts/run_inference.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import os
import json
import logging
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies, DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.analysis.risk import value_at_risk
from src.features.engineer import build_feature_matrix, select_top_features
from src.models.arima_model import arima_predict_test
from src.models.lstm_model import train_lstm, lstm_predict, save_lstm
from src.models.xgboost_model import train_xgboost, save_xgboost
from src.models.ensemble import ensemble_predict, generate_signal, compute_ensemble_metrics
from scripts.push_to_firestore import (
    get_db, write_snapshot, write_technicals,
    update_company_public, write_market_overview,
    download_model_from_storage, prune_old_docs,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()
MODELS_TMP = Path("/tmp/nse_models")


def _download_models(ticker: str) -> bool:
    safe = ticker.replace(".", "_")
    files = [f"{safe}_lstm.pt", f"{safe}_lstm_scaler.pkl", f"{safe}_xgboost.pkl"]
    all_ok = True
    for fname in files:
        ok = download_model_from_storage(
            storage_path=f"models/{fname}",
            local_path=str(MODELS_TMP / fname),
        )
        if not ok:
            log.warning("Model not found in Storage: %s — will train from scratch", fname)
            all_ok = False
    return all_ok


def build_company_result(
    signal: dict,
    metrics: dict,
    actuals: np.ndarray,
    preds: np.ndarray,
    forecast: np.ndarray,
) -> dict:
    return {
        **signal,
        "metrics": metrics,
        "actuals": actuals.tolist(),
        "preds": preds.tolist(),
        "forecast": forecast.tolist(),
    }


def build_technicals_result(df: pd.DataFrame, date_str: str) -> dict:
    try:
        import ta
        close = df["Close"]
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

        rsi    = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        macd_i = ta.trend.MACD(close)
        bb     = ta.volatility.BollingerBands(close)
        sma20  = close.rolling(20).mean().iloc[-1]
        sma50  = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        ema12  = close.ewm(span=12).mean().iloc[-1]
        ema26  = close.ewm(span=26).mean().iloc[-1]

        monthly = (
            df["Close"].resample("ME").last().pct_change() * 100
        ).dropna()
        monthly_heatmap = {
            str(k)[:7]: round(float(v), 2)
            for k, v in monthly.items()
        }

        def _f(x):
            return None if (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)

        return {
            "date": date_str,
            "rsi_14":        _f(rsi),
            "macd":          _f(macd_i.macd().iloc[-1]),
            "macd_signal":   _f(macd_i.macd_signal().iloc[-1]),
            "macd_hist":     _f(macd_i.macd_diff().iloc[-1]),
            "bb_upper":      _f(bb.bollinger_hband().iloc[-1]),
            "bb_mid":        _f(bb.bollinger_mavg().iloc[-1]),
            "bb_lower":      _f(bb.bollinger_lband().iloc[-1]),
            "sma_20":        _f(sma20),
            "sma_50":        _f(sma50),
            "sma_200":       _f(sma200),
            "ema_12":        _f(ema12),
            "ema_26":        _f(ema26),
            "volume":        int(volume.iloc[-1]) if len(volume) else 0,
            "avg_volume_30d": int(volume.tail(30).mean()) if len(volume) else 0,
            "daily_return":  _f(df["Close"].pct_change().iloc[-1] * 100),
            "volatility_30d": _f(df["Close"].pct_change().tail(30).std() * 100),
            "monthly_heatmap": monthly_heatmap,
        }
    except Exception as e:
        log.error("Technicals failed: %s", e)
        return {
            "date": date_str,
            "error": str(e),
            "rsi_14": None,
            "macd": None,
            "macd_signal": None,
            "macd_hist": None,
            "bb_upper": None,
            "bb_mid": None,
            "bb_lower": None,
            "sma_20": None,
            "sma_50": None,
            "sma_200": None,
            "ema_12": None,
            "ema_26": None,
            "volume": 0,
            "avg_volume_30d": 0,
            "daily_return": None,
            "volatility_30d": None,
            "monthly_heatmap": {},
        }


def run_company(company: dict) -> dict | None:
    ticker = company["ticker"]
    safe   = ticker.replace(".", "_")
    csv_p  = PIPELINE_ROOT / "data" / "raw" / company["csv"]
    log.info("Processing %s ...", ticker)

    try:
        raw_df = fetch_nse_data(ticker, csv_path=str(csv_p) if csv_p.exists() else None)
        cleaned_df, _ = clean_ohlcv(raw_df, ticker=ticker)

        ret_df, _   = daily_return_analysis(cleaned_df)
        ma_df       = compute_moving_averages(ret_df)
        var_res     = value_at_risk(cleaned_df, investment=DEFAULT_INVESTMENT,
                                    confidence=DEFAULT_CONFIDENCE)
        feature_df  = build_feature_matrix(ma_df)
        feature_cols = select_top_features(feature_df)

        arima_preds, arima_actuals = arima_predict_test(cleaned_df["Close"])

        model, scaler, test_ds, device = train_lstm(feature_df, feature_cols)
        n_price = 1 + len(feature_cols)
        lstm_preds, lstm_actuals = lstm_predict(model, test_ds, scaler, device, n_price)

        xgb_model, _, xgb_actuals, xgb_preds = train_xgboost(feature_df, feature_cols)

        n = min(len(lstm_preds), len(xgb_preds), len(arima_preds))
        ens_preds   = ensemble_predict(lstm_preds[-n:], xgb_preds[-n:], arima_preds[-n:])
        ens_metrics = compute_ensemble_metrics(lstm_actuals[-n:], ens_preds)

        current_price  = float(cleaned_df["Close"].iloc[-1])
        predicted_next = float(ens_preds[-1]) if len(ens_preds) > 0 else current_price
        var_pct        = var_res["historical_var_pct"]
        signal_result  = generate_signal(current_price, predicted_next, var_pct)

        forecast = [float(predicted_next)] * 30

        snapshot   = build_company_result(signal_result, ens_metrics,
                                          lstm_actuals[-n:], ens_preds, np.array(forecast))
        technicals = build_technicals_result(cleaned_df, TODAY)

        price_preview = cleaned_df["Close"].tail(30).tolist()

        return {
            "ticker": safe,
            "snapshot": snapshot,
            "technicals": technicals,
            "public_update": {
                "current_price": current_price,
                "change_pct_today": float(cleaned_df["Close"].pct_change().iloc[-1] * 100),
                "signal": signal_result["signal"],
                "price_preview": price_preview,
                "last_updated": TODAY,
            },
        }
    except Exception as e:
        log.error("FAILED %s: %s", ticker, e, exc_info=True)
        return None


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
        "date": TODAY,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "signal_distribution": signals,
        "sector_performance": {},
        "nse20_value": None,
        "nse20_change_pct": None,
    }


def main() -> None:
    MODELS_TMP.mkdir(parents=True, exist_ok=True)
    db        = get_db()
    companies = load_companies()
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_company, c): c for c in companies}
        for fut in as_completed(futures):
            res = fut.result()
            if res is None:
                continue
            write_snapshot(db, res["ticker"], TODAY, res["snapshot"])
            write_technicals(db, res["ticker"], TODAY, res["technicals"])
            update_company_public(db, res["ticker"], res["public_update"])
            pruned_s = prune_old_docs(db, res["ticker"], "snapshots")
            pruned_t = prune_old_docs(db, res["ticker"], "technicals")
            if pruned_s or pruned_t:
                log.info("Pruned %d snapshot(s) and %d technical(s) for %s",
                         pruned_s, pruned_t, res["ticker"])
            results.append(res)
            log.info("Written to Firestore: %s", res["ticker"])

    overview = aggregate_market_overview(results)
    write_market_overview(db, TODAY, overview)
    log.info("Market overview written. Done — %d companies processed.", len(results))


if __name__ == "__main__":
    main()
