"""
train_all_companies.py
----------------------
Train LSTM + XGBoost + ARIMA models for every NSE company that has sufficient
archive data, then write signal JSON files and cleaned CSVs locally.

No Firebase / internet connection required.

Usage:
    python train_all_companies.py                   # all 61 companies
    python train_all_companies.py SCOM EQTY KCB     # specific companies
    python train_all_companies.py --skip-lstm        # XGBoost+ARIMA only (much faster)
    python train_all_companies.py --min-days 252     # accept companies with 1+ year of data
    python train_all_companies.py --list             # show which companies have archive data

Output:
    data/cleaned/<CODE>_NR_cleaned.csv   → price history (used by the dashboard)
    data/features/<CODE>_NR_signal.json  → BUY/SELL/HOLD signal + metrics
    models/saved/<CODE>_NR_*.pkl/.pt     → trained model files

How the signal is generated:
    1. Load OHLCV from the NSE archive CSVs (2007-2026)
    2. Clean: remove outliers, fill gaps, validate OHLC logic
    3. Engineer 25+ technical features (RSI, MACD, Bollinger Bands, etc.)
    4. Train LSTM (PyTorch), XGBoost, and ARIMA models
    5. Ensemble: LSTM 25% + XGBoost 60% + ARIMA 15%
    6. Generate signal: predicted_next > current+2% → BUY, < current-2% → SELL
    7. Risk-adjust with Value at Risk (historical 95% VaR)
"""
import sys
import io
import json
import argparse
import logging
import time
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent           # nse_predictor/
PIPELINE = ROOT / "pipeline"               # nse_predictor/pipeline/

# Root FIRST so `import config` finds the root config.py (DATA_CLEANED etc.)
# Pipeline second so `from src.data.*` imports resolve correctly
sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(ROOT))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import numpy as np

from src.data.nse_loader import load_nse_ticker, NSE_ARCHIVE_DIR
from src.data.cleaner import clean_ohlcv, validate_ticker, save_cleaned
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.analysis.risk import value_at_risk
from src.features.engineer import build_feature_matrix, select_top_features
from src.models.arima_model import arima_predict_test
from src.models.xgboost_model import train_xgboost, save_xgboost
from src.models.ensemble import ensemble_predict, generate_signal, compute_ensemble_metrics
from config import (
    DATA_CLEANED, DATA_FEATURES, MODELS_DIR,
    DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE, MIN_TRADING_DAYS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# All 61 NSE companies from the archive
ALL_CODES = [
    "ABSA","ALP","AMAC","BAT","BKG","BOC","BRIT","CARB","CGEN","CIC",
    "COOP","CRWN","CTUM","DTK","EABL","EGAD","EQTY","EVRD","FMLY","FTGH",
    "GLD","HAFR","HFCK","IMH","JUB","KAPC","KCB","KEGN","KNRE","KPC",
    "KPLC","KQ","KUKZ","KURV","LBTY","LIMT","LKL","NBV","NCBA","NMG",
    "NSE","OCH","PORT","SASN","SBIC","SCAN","SCBK","SCOM","SGL","SKL",
    "SLAM","SMER","SMWF","TOTL","TPSE","TRFC","UCHM","UMME","UNGA","WTK","XPRS",
]


def _save_signal(ticker: str, data: dict) -> Path:
    DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    path = DATA_FEATURES / f"{ticker.replace('.', '_')}_signal.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


def train_company(code: str, skip_lstm: bool = False, min_days: int = MIN_TRADING_DAYS) -> dict | None:
    ticker = f"{code}.NR"
    safe   = ticker.replace(".", "_")
    t0     = time.time()

    try:
        # ── 1. Load from archive ────────────────────────────────────────────
        raw_df = load_nse_ticker(ticker, archive_dir=NSE_ARCHIVE_DIR)
    except Exception as e:
        log.warning("%-10s  SKIP — no archive data: %s", code, e)
        return None

    try:
        # ── 2. Clean & validate ─────────────────────────────────────────────
        cleaned_df, report = clean_ohlcv(raw_df, ticker=ticker)
        if report["cleaned_rows"] < min_days:
            log.warning("%-10s  SKIP — only %d trading days (need %d)",
                        code, report["cleaned_rows"], min_days)
            return None

        # ── 3. Analysis ─────────────────────────────────────────────────────
        ret_df, _ = daily_return_analysis(cleaned_df)
        ma_df     = compute_moving_averages(ret_df)
        var_res   = value_at_risk(cleaned_df, investment=DEFAULT_INVESTMENT,
                                  confidence=DEFAULT_CONFIDENCE)

        # ── 4. Feature engineering ──────────────────────────────────────────
        feature_df   = build_feature_matrix(ma_df)
        feature_cols = select_top_features(feature_df)

        # ── 5. ARIMA ────────────────────────────────────────────────────────
        arima_preds, arima_actuals = arima_predict_test(cleaned_df["Close"])

        # ── 6. XGBoost ──────────────────────────────────────────────────────
        xgb_model, _, xgb_actuals, xgb_preds = train_xgboost(feature_df, feature_cols)
        save_xgboost(xgb_model, ticker)

        # ── 7. LSTM (optional) ───────────────────────────────────────────────
        if not skip_lstm:
            from src.models.lstm_model import train_lstm, lstm_predict, save_lstm
            model, scaler, test_ds, device = train_lstm(feature_df, feature_cols)
            n_feats = 1 + len(feature_cols)
            lstm_preds, lstm_actuals = lstm_predict(model, test_ds, scaler, device, n_feats)
            save_lstm(model, scaler, ticker)
        else:
            lstm_preds    = np.array([])
            lstm_actuals  = xgb_actuals

        # ── 8. Ensemble ──────────────────────────────────────────────────────
        if not skip_lstm and len(lstm_preds) > 0:
            n = min(len(lstm_preds), len(xgb_preds), len(arima_preds))
            ens = ensemble_predict(lstm_preds[-n:], xgb_preds[-n:], arima_preds[-n:])
            actuals_for_metrics = lstm_actuals[-n:]
        else:
            # XGBoost-heavy weights when no LSTM
            n = min(len(xgb_preds), len(arima_preds))
            ens = 0.75 * xgb_preds[-n:] + 0.25 * arima_preds[-n:]
            actuals_for_metrics = xgb_actuals[-n:]

        metrics = compute_ensemble_metrics(actuals_for_metrics, ens)

        # ── 9. Signal ────────────────────────────────────────────────────────
        current_price  = float(cleaned_df["Close"].iloc[-1])
        predicted_next = float(ens[-1]) if len(ens) > 0 else current_price
        var_pct        = var_res["historical_var_pct"]
        signal         = generate_signal(current_price, predicted_next, var_pct)

        # ── 10. Save outputs ──────────────────────────────────────────────────
        save_cleaned(cleaned_df, ticker)

        signal_data = {
            **signal,
            "signal_source": "ml",
            "metrics": metrics,
            "model_type": "XGBoost+ARIMA" if skip_lstm else "LSTM+XGBoost+ARIMA",
            "preds":   ens.tolist(),
            "actuals": actuals_for_metrics.tolist(),
        }
        sig_path = _save_signal(ticker, signal_data)

        elapsed = round(time.time() - t0, 1)
        ra = signal["risk_adjusted_signal"]
        log.info("%-10s  %-4s  KES %7.2f → %7.2f  (%+.2f%%)  MAPE=%.1f%%  [%ss]",
                 code, ra, current_price, predicted_next,
                 signal["predicted_change_pct"], metrics.get("mape", 0), elapsed)

        return signal_data

    except Exception as e:
        log.error("%-10s  ERROR: %s", code, e, exc_info=True)
        return None


def list_available(codes: list[str]) -> None:
    print(f"\nChecking archive at: {NSE_ARCHIVE_DIR}\n")
    print(f"{'Code':<8}  {'Days':>6}  {'From':<12}  {'To':<12}  Status")
    print("-" * 56)
    for code in codes:
        try:
            df = load_nse_ticker(f"{code}.NR", archive_dir=NSE_ARCHIVE_DIR)
            status = f"{len(df):>6} days  {str(df.index[0].date()):<12}  {str(df.index[-1].date()):<12}"
            ok = "✓" if len(df) >= MIN_TRADING_DAYS else f"⚠ < {MIN_TRADING_DAYS}"
            print(f"{code:<8}  {status}  {ok}")
        except Exception as e:
            print(f"{code:<8}  {'—':>6}  {'':12}  {'':12}  ✗ {e}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Train ML models for all NSE companies")
    parser.add_argument("codes", nargs="*", default=[],
                        help="NSE codes to train (default: all 61). E.g. SCOM EQTY KCB")
    parser.add_argument("--skip-lstm", action="store_true",
                        help="Skip LSTM — use XGBoost+ARIMA only (3-5× faster)")
    parser.add_argument("--min-days", type=int, default=MIN_TRADING_DAYS,
                        help=f"Minimum trading days required (default: {MIN_TRADING_DAYS})")
    parser.add_argument("--list", action="store_true",
                        help="List archive coverage per company then exit")
    args = parser.parse_args()

    codes = [c.upper().replace(".NR", "") for c in args.codes] if args.codes else ALL_CODES

    if args.list:
        list_available(codes)
        return

    DATA_CLEANED.mkdir(parents=True, exist_ok=True)
    DATA_FEATURES.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    mode = "XGBoost+ARIMA only" if args.skip_lstm else "LSTM+XGBoost+ARIMA"
    log.info("Training %d companies  |  mode: %s  |  min_days: %d",
             len(codes), mode, args.min_days)
    log.info("Outputs → %s  &  %s", DATA_CLEANED, DATA_FEATURES)
    print()

    results = {"ok": [], "skipped": [], "error": []}

    for i, code in enumerate(codes, 1):
        log.info("[%d/%d] %s", i, len(codes), code)
        result = train_company(code, skip_lstm=args.skip_lstm, min_days=args.min_days)
        if result is None:
            results["skipped"].append(code)
        elif "error" in str(result):
            results["error"].append(code)
        else:
            results["ok"].append(code)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  TRAINING COMPLETE")
    print(f"{'='*60}")
    print(f"  Trained successfully : {len(results['ok'])} companies")
    print(f"  Skipped (no data)    : {len(results['skipped'])} companies")
    print(f"  Errors               : {len(results['error'])} companies")
    if results["ok"]:
        print(f"\n  Signals saved to: {DATA_FEATURES}")
        print(f"  Cleaned CSVs at : {DATA_CLEANED}")
    if results["skipped"]:
        print(f"\n  Skipped: {', '.join(results['skipped'])}")
    if results["error"]:
        print(f"\n  Errors : {', '.join(results['error'])}")
    print(f"\n  Refresh the dashboard at http://127.0.0.1:8050 to see updated signals.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
