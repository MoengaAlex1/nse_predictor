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
        high   = df["High"]   if "High"   in df.columns else close
        low    = df["Low"]    if "Low"    in df.columns else close
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(0, index=df.index)

        rsi    = ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1]
        macd_i = ta.trend.MACD(close)
        bb     = ta.volatility.BollingerBands(close)
        sma20  = close.rolling(20).mean().iloc[-1]
        sma50  = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        ema12  = close.ewm(span=12).mean().iloc[-1]
        ema26  = close.ewm(span=26).mean().iloc[-1]

        # ── Expanded indicator set (2026-09-19) ──────────────────────────────
        # ATR: 14-day Average True Range — volatility band a stock is
        #      currently oscillating in (used for stop-loss sizing).
        atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range().iloc[-1]
        # ADX: 14-day trend-strength (0-100). Above 25 = strong trend,
        #      below 20 = ranging market.
        adx_i = ta.trend.ADXIndicator(high, low, close, window=14)
        adx = adx_i.adx().iloc[-1]
        # Stochastic %K/%D — momentum oscillator (0-100). >80 overbought,
        # <20 oversold. Complements RSI for slower-moving stocks.
        stoch_i = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
        stoch_k = stoch_i.stoch().iloc[-1]
        stoch_d = stoch_i.stoch_signal().iloc[-1]
        # VWAP: session-anchored Volume-Weighted Average Price. On daily
        # bars this is the running VWAP over 14 days — a rolling anchor
        # used to gauge whether current price is being paid at a premium
        # or discount vs. weighted intent.
        vwap = ta.volume.VolumeWeightedAveragePrice(high, low, close, volume, window=14).volume_weighted_average_price().iloc[-1]
        # CCI: Commodity Channel Index. > +100 overbought, < -100 oversold.
        cci = ta.trend.CCIIndicator(high, low, close, window=20).cci().iloc[-1]
        # OBV: On-Balance Volume — cumulative signed volume, reveals
        # accumulation/distribution before the price move.
        obv = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume().iloc[-1]

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
            # New indicators — added 2026-09-19.
            "atr_14":           _f(atr),
            "adx_14":           _f(adx),
            "stoch_k":          _f(stoch_k),
            "stoch_d":          _f(stoch_d),
            "vwap_14":          _f(vwap),
            "cci_20":           _f(cci),
            "obv":              _f(obv),
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
            "atr_14": None, "adx_14": None, "stoch_k": None, "stoch_d": None,
            "vwap_14": None, "cci_20": None, "obv": None,
            "volume": 0, "avg_volume_30d": 0,
            "daily_return": None, "volatility_30d": None, "monthly_heatmap": {},
        }
