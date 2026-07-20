# pipeline/scripts/run_daily_update.py
"""
Daily pipeline orchestrator: scrape → retrain XGBoost + ARIMA → inference.

LSTM is NOT retrained here (weekly cadence only — too slow for daily runs).
The most recently uploaded LSTM artifacts are loaded from Firebase Storage.

Steps for each company:
  1. Scrape today's prices (scrape_nse_prices.main).
  2. Load the refreshed CSV from CSVS_TMP.
  3. Run the full feature engineering pipeline.
  4. Retrain XGBoost and ARIMA on the updated data.
  5. Upload the new XGBoost + ARIMA artifacts to Firebase Storage.
  6. Load LSTM from existing weekly artifacts (no retraining).
  7. Run inference (ensemble) and write to Firestore.
  8. Write market overview.

Usage: python pipeline/scripts/run_daily_update.py
Env:   FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
       NSE_TICKERS_FILTER (optional comma-separated list)
"""
import sys
import os
import json
import logging
import tempfile as _tempfile
from pathlib import Path
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
import pandas as pd
import torch
import joblib

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import (
    load_companies,
    DEFAULT_INVESTMENT,
    DEFAULT_CONFIDENCE,
    ENSEMBLE_WEIGHTS,
    SEQUENCE_LENGTH,
    ARTIFACT_SUFFIXES,
)
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.analysis.risk import value_at_risk
from src.features.engineer import (
    build_feature_matrix,
    select_top_features,
    save_feature_cols,
    load_feature_cols,
)
from src.models.lstm_model import (
    NSELSTMModel,
    lstm_predict_next,
    lstm_forecast_30d,
)
from src.models.xgboost_model import train_xgboost, save_xgboost
from src.models.arima_model import train_arima, arima_forecast, save_arima
from src.models.ensemble import ensemble_predict, generate_signal, compute_ensemble_metrics
from src.models.arima_model import arima_predict_test
from src.models.lstm_model import lstm_predict, SequenceDataset
from src.analysis.technicals import build_technicals_result as _build_technicals
from src.analysis.market import aggregate_market_overview
from scripts.push_to_firestore import (
    get_db,
    write_snapshot,
    write_technicals,
    update_company_public,
    write_market_overview,
    upload_model_to_storage,
    download_model_from_storage,
    prune_old_docs,
)
from scripts.scrape_nse_prices import CSVS_TMP, main as scrape_main

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()
MODELS_TMP = Path(_tempfile.gettempdir()) / "nse_models"

# Artifact filenames that must be present for a full model load.
_LSTM_SUFFIXES = ["_lstm.pt", "_lstm_scaler.pkl", "_feature_cols.json"]
_ALL_SUFFIXES = ARTIFACT_SUFFIXES


# ── Storage helpers ───────────────────────────────────────────────────────────

def _download_lstm_artifacts(safe: str) -> bool:
    """Download only the LSTM artifacts from Firebase Storage. Returns True if all found."""
    all_ok = True
    for suffix in _LSTM_SUFFIXES:
        fname = f"{safe}{suffix}"
        ok = download_model_from_storage(
            storage_path=f"models/{fname}",
            local_path=str(MODELS_TMP / fname),
        )
        if not ok:
            log.warning("LSTM artifact not in Storage: %s", fname)
            all_ok = False
    return all_ok


def _upload_xgb_arima(safe: str) -> None:
    """Upload freshly trained XGBoost and ARIMA artifacts to Firebase Storage."""
    for suffix in ["_xgboost.pkl", "_arima.pkl", "_feature_cols.json"]:
        fname = f"{safe}{suffix}"
        local = MODELS_TMP / fname
        if local.exists():
            upload_model_to_storage(str(local), f"models/{fname}")
            log.info("  Uploaded → models/%s", fname)
        else:
            log.warning("  Artifact missing, skipping upload: %s", fname)


# ── Trading-day helpers ───────────────────────────────────────────────────────

def _next_trading_day_local(from_date: date) -> date:
    """First NSE trading day (Mon-Fri) strictly after from_date."""
    d = from_date + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _forecast_trading_dates_local(base: date, n: int) -> list[str]:
    """n consecutive trading-day ISO dates starting the day after base."""
    dates: list[str] = []
    d = base
    while len(dates) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            dates.append(d.isoformat())
    return dates


# ── Per-company pipeline ──────────────────────────────────────────────────────

def run_company(company: dict, csv_override: Path | None = None) -> dict | None:
    """
    Retrain XGBoost + ARIMA on today's data, then run full ensemble inference.

    Parameters
    ----------
    company:
        Entry from companies.json.
    csv_override:
        Path to the freshly scraped CSV. When provided (normal daily-update flow),
        data is loaded from this file; otherwise falls back to repo CSVs.

    Returns a result dict ready for Firestore writes, or None on failure.
    """
    ticker = company["ticker"]
    safe = ticker.replace(".", "_")
    log.info("Processing %s ...", ticker)

    try:
        # ── 1. Load data ──────────────────────────────────────────────────────
        repo_csv = PIPELINE_ROOT.parent / "data" / "raw" / company["csv"]

        if csv_override is not None and csv_override.exists():
            csv_path_str = str(csv_override)
        elif repo_csv.exists():
            csv_path_str = str(repo_csv)
        else:
            csv_path_str = None

        raw_df = fetch_nse_data(ticker, csv_path=csv_path_str)
        # Strip future-dated rows — repo CSVs can contain forward-filled rows
        # past today that would make current_price read from the wrong date.
        _today_ts = pd.Timestamp(date.today())
        raw_df = raw_df[raw_df.index <= _today_ts]
        # Also drop is_stale==1 rows if present (forward-fills from original cleaner)
        if "Is_Stale" in raw_df.columns:
            raw_df = raw_df[raw_df["Is_Stale"] != 1]
        elif "is_stale" in raw_df.columns:
            raw_df = raw_df[raw_df["is_stale"] != 1]
        cleaned_df, _ = clean_ohlcv(raw_df, ticker=ticker)
        ret_df, _ = daily_return_analysis(cleaned_df)
        ma_df = compute_moving_averages(ret_df)
        var_res = value_at_risk(
            cleaned_df,
            investment=DEFAULT_INVESTMENT,
            confidence=DEFAULT_CONFIDENCE,
        )
        feature_df = build_feature_matrix(ma_df)

        # ── 2. Feature selection ──────────────────────────────────────────────
        # Re-derive feature cols if no cached JSON; otherwise use the saved list.
        feat_json = MODELS_TMP / f"{safe}_feature_cols.json"
        if feat_json.exists():
            with open(feat_json, encoding="utf-8") as fh:
                feature_cols = json.load(fh)
            # Rebuild if any saved feature is now absent from current data
            missing = [c for c in feature_cols if c not in feature_df.columns]
            if missing:
                log.warning(
                    "%s: %d saved feature cols missing — reselecting",
                    ticker,
                    len(missing),
                )
                feature_cols = select_top_features(feature_df)
        else:
            feature_cols = select_top_features(feature_df)

        # ── 3. Retrain XGBoost ────────────────────────────────────────────────
        log.info("  Retraining XGBoost for %s ...", ticker)
        xgb_model, _, xgb_actuals, xgb_preds_train = train_xgboost(feature_df, feature_cols)
        save_xgboost(xgb_model, ticker, model_dir=MODELS_TMP)

        # ── 4. Retrain ARIMA ──────────────────────────────────────────────────
        log.info("  Retraining ARIMA for %s ...", ticker)
        arima_fit = train_arima(cleaned_df["Close"], order=(2, 1, 2))
        save_arima(arima_fit, ticker, model_dir=MODELS_TMP)

        # Persist updated feature cols (after possible reselection above)
        save_feature_cols(feature_cols, ticker, model_dir=MODELS_TMP)

        # ── 5. Upload XGBoost + ARIMA artifacts ──────────────────────────────
        _upload_xgb_arima(safe)

        # ── 6. Load LSTM from Storage (no retraining) ─────────────────────────
        device = torch.device("cpu")
        lstm_model = None
        scaler = None

        lstm_pt = MODELS_TMP / f"{safe}_lstm.pt"
        lstm_sc = MODELS_TMP / f"{safe}_lstm_scaler.pkl"

        if lstm_pt.exists() and lstm_sc.exists():
            try:
                n_features = 1 + len(feature_cols)
                lstm_model = NSELSTMModel(n_features)
                state = torch.load(lstm_pt, map_location="cpu", weights_only=True)
                lstm_model.load_state_dict(state)
                lstm_model.eval()
                scaler = joblib.load(lstm_sc)
                log.info("  Loaded LSTM from local cache for %s", ticker)
            except Exception as exc:
                log.warning("  LSTM load failed (%s) — LSTM predictions disabled", exc)
                lstm_model = None
                scaler = None
        else:
            log.warning(
                "  No LSTM artifacts in cache for %s — "
                "run weekly training or trigger run_training.py",
                ticker,
            )

        # ── 7. Next-day predictions ───────────────────────────────────────────
        w_lstm, w_xgb, w_arima = ENSEMBLE_WEIGHTS

        if lstm_model is not None and scaler is not None:
            try:
                lstm_next = lstm_predict_next(
                    lstm_model, feature_df, feature_cols, scaler, device
                )
            except Exception as exc:
                log.warning("%s LSTM predict_next failed (%s) — falling back", ticker, exc)
                lstm_next = float(cleaned_df["Close"].iloc[-1])
        else:
            lstm_next = float(cleaned_df["Close"].iloc[-1])

        last_row = feature_df[feature_cols].iloc[[-1]]
        xgb_next = float(xgb_model.predict(last_row)[0])

        try:
            arima_30d = arima_forecast(arima_fit, steps=30).tolist()
        except Exception as exc:
            log.warning("%s ARIMA forecast failed (%s) — using zeros", ticker, exc)
            arima_30d = [float(cleaned_df["Close"].iloc[-1])] * 30

        arima_next = arima_30d[0]

        # If LSTM is unavailable, redistribute its weight to XGBoost
        if lstm_model is None:
            adjusted_w_xgb = w_xgb + w_lstm
            predicted_next = adjusted_w_xgb * xgb_next + w_arima * arima_next
        else:
            predicted_next = w_lstm * lstm_next + w_xgb * xgb_next + w_arima * arima_next

        # ── 8. 30-day forecast ────────────────────────────────────────────────
        if lstm_model is not None and scaler is not None:
            try:
                lstm_30d = lstm_forecast_30d(
                    lstm_model, feature_df, feature_cols, scaler, device
                )
                forecast_30d = [
                    round(w_lstm * l + w_arima * a + w_xgb * xgb_next, 4)
                    for l, a in zip(lstm_30d, arima_30d)
                ]
            except Exception as exc:
                log.warning(
                    "%s LSTM 30d forecast failed (%s) — using ARIMA only", ticker, exc
                )
                forecast_30d = [round(float(v), 4) for v in arima_30d]
        else:
            forecast_30d = [round(float(v), 4) for v in arima_30d]

        # ── 9. Historical ensemble metrics (diagnostic) ───────────────────────
        try:
            cols_for_eval = ["Close"] + feature_cols
            data_eval = feature_df[cols_for_eval].values.astype(float)
            split = int(len(data_eval) * 0.80)

            if lstm_model is not None and scaler is not None:
                test_scaled = scaler.transform(data_eval[split:])
                test_ds = SequenceDataset(test_scaled)

                if len(test_ds) >= 2:
                    lstm_preds_hist, lstm_act_hist = lstm_predict(
                        lstm_model, test_ds, scaler, device, 1 + len(feature_cols)
                    )
                else:
                    lstm_preds_hist = np.array([])
                    lstm_act_hist = np.array([])
            else:
                lstm_preds_hist = np.array([])
                lstm_act_hist = np.array([])

            arima_preds_hist, arima_act_hist = arima_predict_test(cleaned_df["Close"])
            xgb_preds_hist = xgb_model.predict(feature_df[feature_cols].iloc[split:])

            n = min(
                len(lstm_preds_hist) if len(lstm_preds_hist) else len(xgb_preds_hist),
                len(xgb_preds_hist),
                len(arima_preds_hist),
            )

            if n >= 2 and len(lstm_preds_hist) >= n:
                ens_h = ensemble_predict(
                    lstm_preds_hist[-n:], xgb_preds_hist[-n:], arima_preds_hist[-n:]
                )
                ens_metrics = compute_ensemble_metrics(lstm_act_hist[-n:], ens_h)
                actuals_out = lstm_act_hist[-n:].tolist()
                preds_out = ens_h.tolist()
            elif n >= 2:
                # LSTM unavailable — use XGBoost actuals for metric alignment
                xgb_actuals_hist = feature_df["Close"].iloc[split:].values
                n2 = min(len(xgb_actuals_hist), len(arima_preds_hist))
                ens_h = (w_xgb + w_lstm) * xgb_preds_hist[-n2:] + w_arima * arima_preds_hist[-n2:]
                ens_metrics = compute_ensemble_metrics(xgb_actuals_hist[-n2:], ens_h)
                actuals_out = xgb_actuals_hist[-n2:].tolist()
                preds_out = ens_h.tolist()
            else:
                ens_metrics = {
                    "rmse": None, "mae": None,
                    "mape": None, "directional_accuracy": None,
                }
                actuals_out = []
                preds_out = []

        except Exception as exc:
            log.warning("%s metrics evaluation failed: %s", ticker, exc)
            ens_metrics = {
                "rmse": None, "mae": None,
                "mape": None, "directional_accuracy": None,
            }
            actuals_out = []
            preds_out = []

        # ── 10. Signal generation ─────────────────────────────────────────────
        current_price = float(cleaned_df["Close"].iloc[-1])
        var_pct = var_res["historical_var_pct"]
        technicals = _build_technicals(cleaned_df, TODAY)
        signal_result = generate_signal(
            current_price, predicted_next, var_pct,
            lstm_next=lstm_next, xgb_next=xgb_next, arima_next=arima_next,
            technicals=technicals,
        )

        # ── 11. Build Firestore payloads ──────────────────────────────────────
        target_date = _next_trading_day_local(date.today())
        forecast_dates = _forecast_trading_dates_local(date.today(), len(forecast_30d))

        snapshot = {
            **signal_result,
            "run_date":       TODAY,
            "next_trading_day": target_date.isoformat(),
            "forecast_dates": forecast_dates,
            "metrics":    ens_metrics,
            "actuals":    actuals_out,
            "preds":      preds_out,
            "forecast":   forecast_30d,
            "lstm_next":  round(lstm_next, 4),
            "xgb_next":   round(xgb_next, 4),
            "arima_next": round(arima_next, 4),
        }

        # Compare last 2 distinct close prices from the actual (non-forward-filled) data.
        # cleaned_df forward-fills weekend/holiday gaps so pct_change() between the
        # last two rows is always safe — but if there was a multi-day data gap the
        # forward-filled rows will show 0% change and only the new real row will
        # show the full period move.  We use the last two *unique* prices instead.
        _real_closes = cleaned_df["Close"].dropna()
        if len(_real_closes) >= 2:
            _prev_price = float(_real_closes.iloc[-2])
            change_pct = (_prev_price > 0) and float(
                (current_price - _prev_price) / _prev_price * 100
            ) or 0.0
        else:
            change_pct = 0.0
        # NSE circuit breaker is ±9.9%; cap display at ±15% to absorb rare edge cases
        change_pct = max(-15.0, min(15.0, change_pct))

        # Build price_history with dates (last 90 real trading days)
        today_ts = pd.Timestamp(date.today())
        hist_df = cleaned_df.copy()
        if "Is_Stale" in hist_df.columns:
            hist_df = hist_df[hist_df["Is_Stale"] != 1]
        hist_df = hist_df[hist_df.index <= today_ts]
        hist_df = hist_df[hist_df.index.dayofweek < 5]
        price_history = [
            {"date": idx.strftime("%Y-%m-%d"), "price": round(float(val), 4)}
            for idx, val in hist_df["Close"].tail(90).items()
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
                "last_updated": TODAY,
            },
        }

    except Exception as exc:
        log.error("FAILED %s: %s", ticker, exc, exc_info=True)
        return None


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    MODELS_TMP.mkdir(parents=True, exist_ok=True)

    db = get_db()
    companies = load_companies()

    ticker_filter = os.environ.get("NSE_TICKERS_FILTER", "").strip()
    if ticker_filter:
        allowed = {t.strip().upper() for t in ticker_filter.split(",") if t.strip()}
        companies = [c for c in companies if c["ticker"].upper() in allowed]
        log.info(
            "NSE_TICKERS_FILTER active — running %d/%d companies: %s",
            len(companies),
            len(load_companies()),
            ", ".join(allowed),
        )

    # ── Step 1: Scrape today's prices (or download cached CSVs) ──────────────
    skip_scrape = os.environ.get("SKIP_SCRAPE", "").lower() in ("1", "true", "yes")
    if skip_scrape:
        log.info("=== Step 1: SKIP_SCRAPE=1 — downloading cached CSVs from Storage ===")
        # Download existing CSVs so run_company can use them; no new price fetch
        from scripts.scrape_nse_prices import CSVS_TMP as _CSVS_TMP
        from scripts.push_to_firestore import download_model_from_storage as _dl
        import shutil as _shutil
        _CSVS_TMP.mkdir(parents=True, exist_ok=True)
        for _co in companies:
            _safe = _co["ticker"].replace(".", "_")
            _dst  = _CSVS_TMP / f"{_safe}_cleaned.csv"
            if not _dst.exists():
                ok = _dl(f"data/cleaned/{_safe}_cleaned.csv", str(_dst))
                if not ok:
                    _repo = PIPELINE_ROOT.parent / "data" / "cleaned" / f"{_safe}_cleaned.csv"
                    if _repo.exists():
                        _shutil.copy2(_repo, _dst)
        log.info("CSV download complete.")
    else:
        log.info("=== Step 1: Scraping NSE prices (NSE → stooq → yfinance) ===")
        scrape_results = scrape_main()
        scraped = sum(1 for r in scrape_results.values() if r["scraped"])
        log.info("Scraping complete: %d/%d companies updated.", scraped, len(scrape_results))

    # ── Step 2: Pre-download LSTM artifacts (sequential, avoids Storage races) ─
    log.info("=== Step 2: Pre-downloading LSTM artifacts for %d companies ===", len(companies))
    for company in companies:
        safe = company["ticker"].replace(".", "_")
        lstm_pt = MODELS_TMP / f"{safe}_lstm.pt"
        if not lstm_pt.exists():
            _download_lstm_artifacts(safe)

    # ── Step 3: Retrain XGBoost + ARIMA + run inference (parallel, 4 workers) ─
    log.info(
        "=== Step 3: Retraining XGBoost/ARIMA + inference for %d companies ===",
        len(companies),
    )
    results: list[dict] = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        def _submit(company: dict) -> Any:
            safe = company["ticker"].replace(".", "_")
            csv_local = CSVS_TMP / f"{safe}_cleaned.csv"
            csv_override = csv_local if csv_local.exists() else None
            return pool.submit(run_company, company, csv_override)

        futures = {_submit(c): c for c in companies}

        for fut in as_completed(futures):
            company = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:
                log.error(
                    "Unexpected error for %s: %s",
                    company["ticker"],
                    exc,
                    exc_info=True,
                )
                res = None

            if res is None:
                continue

            write_snapshot(db, res["ticker"], TODAY, res["snapshot"])
            write_technicals(db, res["ticker"], TODAY, res["technicals"])
            update_company_public(db, res["ticker"], res["public_update"])
            ps = prune_old_docs(db, res["ticker"], "snapshots")
            pt = prune_old_docs(db, res["ticker"], "technicals")
            if ps or pt:
                log.info(
                    "  Pruned %d snapshot(s), %d technical(s) for %s",
                    ps,
                    pt,
                    res["ticker"],
                )
            results.append(res)
            log.info(
                "Written to Firestore: %-20s signal=%s  price=%.4f",
                res["ticker"],
                res["public_update"]["signal"],
                res["public_update"]["current_price"],
            )

    # ── Step 4: Market overview ────────────────────────────────────────────────
    log.info("=== Step 4: Writing market overview ===")
    overview = aggregate_market_overview(results, TODAY)
    write_market_overview(db, TODAY, overview)

    log.info(
        "Daily update complete — %d/%d companies processed. "
        "Signals: BUY=%d HOLD=%d SELL=%d",
        len(results),
        len(companies),
        overview["signal_distribution"].get("BUY", 0),
        overview["signal_distribution"].get("HOLD", 0),
        overview["signal_distribution"].get("SELL", 0),
    )


if __name__ == "__main__":
    main()
