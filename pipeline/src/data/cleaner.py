import sys
import io
import pandas as pd
import numpy as np
from pathlib import Path
from config import (DATA_CLEANED, MIN_TRADING_DAYS, MIN_VOLUME_PCT,
                    MAX_STALE_RUN, CLOSE_COMPLETENESS)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def clean_ohlcv(df: pd.DataFrame, ticker: str = "") -> tuple[pd.DataFrame, dict]:
    report = {"ticker": ticker, "original_rows": len(df)}

    # ── Step 1: Standardize columns ─────────────────────────────────────────
    df = df.copy()
    df.columns = [c.strip().title() if c != "Ticker" else c for c in df.columns]
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing columns: {missing_cols}")

    # ── Step 2: Drop rows with any negative price ────────────────────────────
    df = df[(df[["Open", "High", "Low", "Close"]] >= 0).all(axis=1)]

    # ── Step 3: Drop duplicated dates ────────────────────────────────────────
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()

    # ── Step 4: Fill missing trading dates (business day alignment) ──────────
    full_range = pd.date_range(df.index.min(), df.index.max(), freq="B")
    df = df.reindex(full_range)
    df.index.name = "Date"

    # ── Step 5: Forward-fill missing OHLCV ──────────────────────────────────
    price_cols = ["Open", "High", "Low", "Close"]
    df[price_cols] = df[price_cols].ffill()
    df["Volume"] = df["Volume"].fillna(0)

    # ── Step 6: Tag stale price days (std == 0 over 3-day rolling window) ───
    df["is_stale"] = (df["Close"].rolling(3).std() == 0).astype(int)

    # Check for stale runs exceeding the limit
    stale_run = (df["is_stale"]
                 .groupby((df["is_stale"] != df["is_stale"].shift()).cumsum())
                 .transform("sum"))
    max_stale_run = int(stale_run.max()) if not stale_run.empty else 0
    if max_stale_run > MAX_STALE_RUN:
        print(f"  [WARN] [{ticker}] Max consecutive stale days: {max_stale_run} > {MAX_STALE_RUN} (liquidity warning)")

    # ── Step 7: Outlier detection (3×IQR on Close) ──────────────────────────
    Q1 = df["Close"].quantile(0.25)
    Q3 = df["Close"].quantile(0.75)
    IQR = Q3 - Q1
    lower, upper = Q1 - 3 * IQR, Q3 + 3 * IQR
    df["is_outlier"] = ((df["Close"] < lower) | (df["Close"] > upper)).astype(int)
    report["outlier_count"] = int(df["is_outlier"].sum())

    # Fix data-entry errors: outlier rows where Close is also wildly inconsistent
    # with the same row's High/Low (impossible on NSE with ±9.9% daily band).
    # Genuine price spikes have coherent OHLC; typos like 25150 vs High=255 do not.
    data_errors = (df["is_outlier"] == 1) & (
        (df["Close"] > df["High"] * 2) | (df["Close"] < df["Low"] / 2)
    )
    if data_errors.any():
        n_err = int(data_errors.sum())
        print(f"  [FIX] [{ticker}] Correcting {n_err} OHLC-inconsistent close(s) via forward-fill")
        df.loc[data_errors, "Close"] = np.nan
        df["Close"] = df["Close"].ffill()
        # Re-tag outliers on the corrected series
        df["is_outlier"] = ((df["Close"] < lower) | (df["Close"] > upper)).astype(int)

    # ── Step 8: Validate OHLC logic ─────────────────────────────────────────
    invalid_ohlc = df[df["High"] < df["Low"]]
    df = df.drop(invalid_ohlc.index)

    # ── Step 9: Drop leading NaN rows ────────────────────────────────────────
    df = df.dropna(subset=["Close"])

    report["cleaned_rows"] = len(df)
    report["stale_days"] = int(df["is_stale"].sum())
    report["completeness_pct"] = round(
        report["cleaned_rows"] / max(report["original_rows"], 1) * 100, 2
    )

    print(f"\n[{ticker}] Data Quality Report:")
    for k, v in report.items():
        print(f"  {k}: {v}")

    return df, report


def validate_ticker(df: pd.DataFrame, report: dict) -> bool:
    ticker = report.get("ticker", "?")
    checks = []

    rows_ok = report["cleaned_rows"] >= MIN_TRADING_DAYS
    checks.append(("min_trading_days", rows_ok,
                   f"{report['cleaned_rows']} / {MIN_TRADING_DAYS} required"))

    close_ok = report["completeness_pct"] / 100 >= CLOSE_COMPLETENESS
    checks.append(("close_completeness", close_ok,
                   f"{report['completeness_pct']}% / {CLOSE_COMPLETENESS*100}% required"))

    vol_days = int((df["Volume"] > 0).sum())
    vol_ok = vol_days / max(len(df), 1) >= MIN_VOLUME_PCT
    checks.append(("volume_liquidity", vol_ok,
                   f"{vol_days}/{len(df)} days with Volume>0"))

    passed = all(c[1] for c in checks)
    status = "PASS" if passed else "FAIL"
    print(f"\n[{ticker}] Validation: {status}")
    for name, ok, detail in checks:
        print(f"  {'[PASS]' if ok else '[FAIL]'} {name}: {detail}")
    return passed


def save_cleaned(df: pd.DataFrame, ticker: str) -> Path:
    DATA_CLEANED.mkdir(parents=True, exist_ok=True)
    path = DATA_CLEANED / f"{ticker.replace('.', '_')}_cleaned.csv"
    df.to_csv(path)
    return path
