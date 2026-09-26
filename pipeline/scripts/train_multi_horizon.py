"""
Train per-ticker LightGBM multi-horizon regressors (1M/3M/6M/9M/12M).

Sits alongside the existing LSTM/XGB/ARIMA training. Doesn't touch
those models — the multi-horizon LightGBMs are new artefacts that
run_inference loads separately and reports as `horizon_predictions`
on each snapshot.

For every listed ticker:
  1. Load cleaned price history from disk (populated by
     the daily pipeline / archive_disclosures).
  2. Build the existing technical feature matrix (same call as the
     LSTM/XGB path so we don't drift).
  3. Fetch fundamentals + financials + macro from Firestore and add
     them as columns via add_fundamental_columns (point-in-time safe).
  4. Fit one LightGBM per horizon in HORIZONS, walk-forward backtest,
     save to MODELS_DIR/{ticker}_mhgbm_{key}.pkl + meta.

Usage:
    python pipeline/scripts/train_multi_horizon.py [--tickers ABSA SCOM] [--min-days 400]

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
PIPELINE_ROOT = REPO_ROOT / "pipeline"
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies, MODELS_DIR
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.returns import daily_return_analysis
from src.analysis.moving_averages import compute_moving_averages
from src.features.engineer import build_feature_matrix, select_top_features
from src.features.fundamental_features import (
    add_fundamental_columns, FUNDAMENTAL_COLUMNS,
)
from src.models.multi_horizon_gbm import (
    train_multi_horizon, save_multi_horizon, HORIZONS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)


def _fetch_firestore_context(ticker_short: str) -> tuple[dict, dict, dict]:
    """Firestore docs for the fundamental feature builder. Lazy import
    so a --dry-run without credentials still exercises everything else."""
    try:
        from scripts.push_to_firestore import get_db
        db = get_db()
    except Exception as e:  # noqa: BLE001
        log.warning("%s: Firestore init failed (%s) — training on price+technicals only", ticker_short, e)
        return {}, {}, {}

    fin = {}
    fund = {}
    macro = {}
    try:
        fd = db.collection("financials").document(ticker_short).get()
        if fd.exists: fin = fd.to_dict() or {}
        ff = db.collection("fundamentals").document(ticker_short).get()
        if ff.exists: fund = ff.to_dict() or {}
        fm = db.collection("macro").document("kenya").get()
        if fm.exists: macro = fm.to_dict() or {}
    except Exception as e:  # noqa: BLE001
        log.warning("%s: fundamentals read failed: %s", ticker_short, e)
    return fin, fund, macro


def train_one(ticker: str, min_days: int) -> dict | None:
    """Train + save all horizon models for one ticker. Returns the
    per-horizon backtest summary."""
    t0 = time.time()
    company = None
    for c in load_companies():
        if c.get("ticker") == ticker or c.get("short") == ticker:
            company = c
            break
    if company is None:
        log.warning("%s: not in companies config, skipping", ticker)
        return None
    short = company["short"]

    try:
        # CI-safe source: fetch_nse_data pulls from RTDB (or a local CSV
        # if one is present in the runner's tmpfs). The archive-based
        # loader used in local dev needs Downloads/archive to exist,
        # which the GitHub Actions runner doesn't have.
        raw_df = fetch_nse_data(ticker, csv_path=None)
    except Exception as e:  # noqa: BLE001
        log.warning("%s: no price data (%s)", short, e)
        return None

    try:
        cleaned_df, report = clean_ohlcv(raw_df, ticker=ticker)
        if report["cleaned_rows"] < min_days:
            log.warning("%s: only %d rows (need %d) — skipping", short, report["cleaned_rows"], min_days)
            return None

        ret_df, _ = daily_return_analysis(cleaned_df)
        ma_df = compute_moving_averages(ret_df)
        feature_df = build_feature_matrix(ma_df)
        # Same top-feature selection the existing XGB/LSTM path uses so
        # the fundamental columns are added on top of a comparable base.
        tech_cols = select_top_features(feature_df)

        # Fetch + broadcast fundamentals across every row of history.
        # add_fundamental_columns writes columns in place and is
        # point-in-time safe (announcements after date T excluded from
        # the row at T).
        fin, fund, macro = _fetch_firestore_context(short)
        add_fundamental_columns(feature_df, fin, fund, macro)

        feature_cols = tech_cols + FUNDAMENTAL_COLUMNS

        models, report = train_multi_horizon(
            ticker=short,
            feature_df=feature_df,
            feature_cols=feature_cols,
            horizons=HORIZONS,
        )
        if not models:
            log.warning("%s: no horizon models produced (LightGBM unavailable or insufficient data)", short)
            return None

        save_multi_horizon(short, models, report, MODELS_DIR)
        log.info("%-10s  trained %d horizons in %.1fs", short, len(models), time.time() - t0)
        return report.to_json()
    except Exception as e:  # noqa: BLE001
        log.exception("%s: training failed: %s", short, e)
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*", help="Space-separated ticker codes (default: all)")
    parser.add_argument("--min-days", type=int, default=400,
                        help="Skip tickers with fewer clean rows than this (default: 400 ≈ 18 months)")
    args = parser.parse_args()

    companies = load_companies()
    if args.tickers:
        wanted = {t.upper() for t in args.tickers}
        companies = [c for c in companies if c.get("ticker") in wanted or c.get("short") in wanted]

    trained: dict[str, dict] = {}
    for c in companies:
        tk = c.get("ticker") or c.get("short")
        if not tk:
            continue
        report = train_one(tk, args.min_days)
        if report:
            trained[c["short"]] = report

    log.info("=== Done ===")
    log.info("  trained %d tickers", len(trained))
    # Aggregate per-horizon MAPE so a run reports which horizons are
    # trustworthy vs which are noise.
    for key in HORIZONS:
        mape_vals = [t["horizons"][key]["mape"] for t in trained.values()
                     if key in t.get("horizons", {}) and t["horizons"][key].get("mape") is not None]
        hit_vals = [t["horizons"][key]["direction_hit"] for t in trained.values()
                    if key in t.get("horizons", {}) and t["horizons"][key].get("direction_hit") is not None]
        if mape_vals:
            median_mae = sorted(mape_vals)[len(mape_vals) // 2]
            median_hit = sorted(hit_vals)[len(hit_vals) // 2] if hit_vals else None
            hit_str = f"{median_hit * 100:.0f}%" if median_hit is not None else "—"
            # "mape" is really MAE in percentage points now — see the
            # comment in _train_one_horizon.
            log.info("  %s  median MAE=%.1fpp   direction hit=%s   (n=%d tickers)",
                     key, median_mae, hit_str, len(mape_vals))


if __name__ == "__main__":
    main()
