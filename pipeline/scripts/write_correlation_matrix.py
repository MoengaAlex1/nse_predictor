"""
Compute the 60-day rolling cross-stock correlation matrix on daily log
returns and write it to market_overview/correlation_60d so the Portfolio
Builder can penalise highly-correlated combinations.

The heavy math already exists in pipeline/src/analysis/correlation.py
(correlation_analysis). This script wires it to real ticker data pulled
via fetch_nse_data (CI-safe RTDB source, same path run_inference uses)
and stores the result as a nested map:

    market_overview/correlation_60d = {
      updated_at: ISO,
      window_days: 60,
      tickers: ["ABSA", "SCOM", ...],
      matrix: { "ABSA": { "SCOM": 0.42, "KCB": 0.71, ... }, ... },
    }

Writes ONE doc — small enough for one Firestore read from the frontend
(which is important; a per-pair subcollection would be 60×60 = 3600
reads per Planner load).

Usage:
    python pipeline/scripts/write_correlation_matrix.py [--window 60]
                                                        [--min-days 90]
                                                        [--dry-run]

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_RTDB_URL
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
PIPELINE_ROOT = REPO_ROOT / "pipeline"
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

import pandas as pd

from config import load_companies
from src.data.fetcher import fetch_nse_data
from src.data.cleaner import clean_ohlcv
from src.analysis.correlation import correlation_analysis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, default=60,
                        help="Trailing trading-day window for correlation (default: 60 ≈ 3 months)")
    parser.add_argument("--min-days", type=int, default=90,
                        help="Skip tickers with fewer clean rows than this")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip Firestore write")
    args = parser.parse_args()

    companies = load_companies()
    stock_data: dict[str, pd.DataFrame] = {}

    for c in companies:
        tk = c.get("ticker") or c.get("short")
        short = c.get("short")
        if not tk or not short:
            continue
        try:
            raw = fetch_nse_data(tk, csv_path=None)
            cleaned, report = clean_ohlcv(raw, ticker=tk)
            if report["cleaned_rows"] < args.min_days:
                log.warning("%s: only %d clean rows — skip", short, report["cleaned_rows"])
                continue
            # Trailing window only. Correlation on the whole history would
            # weight 2015 volatility clusters against 2026's — regime
            # drift makes that meaningless for a portfolio built today.
            tail = cleaned["Close"].tail(args.window + 1)   # +1 to survive the shift(1) inside correlation_analysis
            if len(tail) < args.window + 1:
                continue
            stock_data[short] = pd.DataFrame({"Close": tail.values}, index=tail.index)
        except Exception as e:  # noqa: BLE001
            log.warning("%s: data pull failed (%s)", short, e)

    log.info("Correlating %d tickers over trailing %d days", len(stock_data), args.window)
    if len(stock_data) < 5:
        log.error("Too few tickers with usable data (%d) — abort", len(stock_data))
        sys.exit(1)

    corr = correlation_analysis(stock_data)   # returns pd.DataFrame Pearson

    # Serialise as {ticker_a: {ticker_b: r}} — matches how the frontend
    # will index it (universe.forEach ticker → get its row).
    tickers = corr.columns.tolist()
    matrix: dict[str, dict[str, float]] = {}
    for a in tickers:
        row: dict[str, float] = {}
        for b in tickers:
            if a == b:
                continue   # self-correlation is always 1, waste of bytes
            v = corr.loc[a, b]
            if pd.isna(v):
                continue
            row[b] = round(float(v), 4)
        matrix[a] = row

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": args.window,
        "tickers": tickers,
        "matrix": matrix,
    }

    if args.dry_run:
        log.info("[dry] would write market_overview/correlation_60d — %d tickers, %d matrix entries",
                 len(tickers), sum(len(r) for r in matrix.values()))
        # Sample a couple of pairs so a dry run has a useful signal.
        sample = tickers[:3]
        for a in sample:
            for b in sample:
                if a != b and b in matrix[a]:
                    log.info("  ρ(%s, %s) = %s", a, b, matrix[a][b])
        return

    from pipeline.scripts.firebase_client import get_firestore
    db = get_firestore()
    db.collection("market_overview").document("correlation_60d").set(payload)
    log.info("Wrote market_overview/correlation_60d (tickers=%d)", len(tickers))


if __name__ == "__main__":
    main()
