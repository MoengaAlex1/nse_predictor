# pipeline/src/analysis/technicals.py
"""Shared technical-indicator builder used by both inference and daily-update pipelines."""
import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def build_technicals_result(df: pd.DataFrame, date_str: str) -> dict:
    """Compute a full set of technical indicators for a price/volume dataframe.

    Parameters
    ----------
    df:
        DataFrame with at minimum a 'Close' column and a DatetimeIndex.
        A 'Volume' column is used when present; otherwise volume fields default to 0.
    date_str:
        ISO date string to embed as the 'date' key in the result dict.
    """
    try:
        import ta
        close  = df["Close"]
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

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

        def _f(x: float) -> float | None:
            return None if (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)

        return {
            "date":             date_str,
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
    except Exception as exc:
        log.error("Technicals computation failed: %s", exc)
        return {
            "date": date_str, "error": str(exc),
            "rsi_14": None, "macd": None, "macd_signal": None, "macd_hist": None,
            "bb_upper": None, "bb_mid": None, "bb_lower": None,
            "sma_20": None, "sma_50": None, "sma_200": None,
            "ema_12": None, "ema_26": None,
            "volume": 0, "avg_volume_30d": 0,
            "daily_return": None, "volatility_30d": None, "monthly_heatmap": {},
        }
