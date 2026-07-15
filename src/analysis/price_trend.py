import pandas as pd
import numpy as np


def max_drawdown(price_series: pd.Series) -> float:
    rolling_max = price_series.cummax()
    drawdown = (price_series - rolling_max) / rolling_max
    return float(drawdown.min())


def price_change_analysis(df: pd.DataFrame) -> dict:
    close = df["Close"].dropna()
    start_price = float(close.iloc[0])
    end_price = float(close.iloc[-1])
    n_years = len(close) / 252

    return {
        "start_price":       round(start_price, 2),
        "end_price":         round(end_price, 2),
        "absolute_change":   round(end_price - start_price, 2),
        "pct_change":        round((end_price / start_price - 1) * 100, 2),
        "cagr_pct":          round(((end_price / start_price) ** (1 / n_years) - 1) * 100, 2),
        "max_drawdown_pct":  round(max_drawdown(close) * 100, 2),
        "all_time_high":     round(float(close.max()), 2),
        "all_time_low":      round(float(close.min()), 2),
        "period_start":      str(close.index[0].date()),
        "period_end":        str(close.index[-1].date()),
        "trading_days":      len(close),
    }
