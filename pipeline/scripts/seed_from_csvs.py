"""
seed_from_csvs.py

Read every *_cleaned.csv from data/cleaned/ and push real data to Firestore:
  - companies/{safe}: current_price, change_pct_today, price_preview (30d), signal=HOLD
  - companies/{safe}/technicals/{date}: RSI, MACD, SMAs, EMAs, monthly heatmap
  - market_overview/{date}: top gainers/losers, signal distribution

Run locally with:
  $env:FIREBASE_SERVICE_ACCOUNT_JSON = Get-Content path\to\key.json -Raw
  $env:FIREBASE_STORAGE_BUCKET = "nse-market-dashboard.firebasestorage.app"
  python pipeline/scripts/seed_from_csvs.py
"""
import sys
import os
import logging
from pathlib import Path
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies, DATA_CLEANED
from scripts.push_to_firestore import (
    get_db,
    write_technicals,
    update_company_public,
    write_market_overview,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()


def _load_csv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            return None
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, format="mixed")
        df = df.set_index(date_col).sort_index()
        df.index.name = "Date"
        if "Close" not in df.columns:
            return None
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        df = df.dropna(subset=["Close"])
        return df
    except Exception as e:
        log.warning("Failed to load %s: %s", path.name, e)
        return None


def _build_technicals(df: pd.DataFrame) -> dict:
    try:
        import ta
        close = df["Close"]
        volume = df["Volume"].fillna(0) if "Volume" in df.columns else pd.Series(0, index=df.index)

        rsi    = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        macd_i = ta.trend.MACD(close)
        bb     = ta.volatility.BollingerBands(close)
        sma20  = close.rolling(20).mean().iloc[-1]
        sma50  = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        ema12  = close.ewm(span=12).mean().iloc[-1]
        ema26  = close.ewm(span=26).mean().iloc[-1]

        monthly = (df["Close"].resample("ME").last().pct_change() * 100).dropna()
        monthly_heatmap = {str(k)[:7]: round(float(v), 2) for k, v in monthly.items()}

        def _f(x: Any) -> float | None:
            try:
                v = float(x)
                return None if np.isnan(v) else round(v, 4)
            except Exception:
                return None

        return {
            "date":             TODAY,
            "rsi_14":           _f(rsi),
            "macd":             _f(macd_i.macd().iloc[-1]),
            "macd_signal":      _f(macd_i.macd_signal().iloc[-1]),
            "macd_hist":        _f(macd_i.macd_diff().iloc[-1]),
            "bb_upper":         _f(bb.bollinger_hband().iloc[-1]),
            "bb_mid":           _f(bb.bollinger_mavg().iloc[-1]),
            "bb_lower":         _f(bb.bollinger_lband().iloc[-1]),
            "sma_20":           _f(sma20),
            "sma_50":           _f(sma50),
            "sma_200":          _f(sma200),
            "ema_12":           _f(ema12),
            "ema_26":           _f(ema26),
            "volume":           int(volume.iloc[-1]) if len(volume) else 0,
            "avg_volume_30d":   int(volume.tail(30).mean()) if len(volume) else 0,
            "daily_return":     _f(df["Close"].pct_change().iloc[-1] * 100),
            "volatility_30d":   _f(df["Close"].pct_change().tail(30).std() * 100),
            "monthly_heatmap":  monthly_heatmap,
        }
    except Exception as e:
        log.warning("Technicals failed: %s", e)
        return {"date": TODAY, "monthly_heatmap": {}}


def main() -> None:
    db = get_db()
    companies = load_companies()
    company_map = {c["ticker"].replace(".", "_"): c for c in companies}

    rows: list[tuple[str, float]] = []
    processed = 0

    for csv_path in sorted(DATA_CLEANED.glob("*_cleaned.csv")):
        safe = csv_path.stem.replace("_cleaned", "")
        company = company_map.get(safe)
        if company is None:
            log.warning("No company entry for %s — skipping", safe)
            continue

        df = _load_csv(csv_path)
        if df is None or len(df) < 5:
            log.warning("%s: too little data — skipping", safe)
            continue

        current_price = float(df["Close"].iloc[-1])
        change_pct = float(df["Close"].pct_change().iloc[-1] * 100)

        hist_90 = df["Close"].tail(90)
        price_history = [
            {"date": idx.strftime("%Y-%m-%d"), "price": round(float(val), 4)}
            for idx, val in hist_90.items()
        ]

        public_update = {
            "current_price":    round(current_price, 4),
            "change_pct_today": round(change_pct, 4),
            "signal":           "HOLD",
            "price_history":    price_history,
            "price_preview":    [p["price"] for p in price_history[-30:]],
            "last_updated":     TODAY,
        }
        update_company_public(db, safe, public_update)

        technicals = _build_technicals(df)
        write_technicals(db, safe, TODAY, technicals)

        rows.append((safe, change_pct))
        processed += 1
        log.info(
            "%-20s  price=%-10.4f  change=%+.2f%%  rows=%d",
            safe, current_price, change_pct, len(df),
        )

    rows.sort(key=lambda x: x[1], reverse=True)
    overview = {
        "date":                TODAY,
        "top_gainers":         [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[:5]],
        "top_losers":          [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[-5:]],
        "signal_distribution": {"BUY": 0, "HOLD": processed, "SELL": 0},
        "sector_performance":  {},
        "nse20_value":         None,
        "nse20_change_pct":    None,
    }
    write_market_overview(db, TODAY, overview)

    log.info("Done — seeded %d/%d companies to Firestore.", processed, len(companies))


if __name__ == "__main__":
    main()
