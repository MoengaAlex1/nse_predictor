import pandas as pd
import numpy as np


def daily_return_analysis(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = df.copy()
    df["daily_return"]      = df["Close"].pct_change()
    df["log_return"]        = np.log(df["Close"] / df["Close"].shift(1))
    df["cumulative_return"] = (1 + df["daily_return"]).cumprod() - 1

    ret = df["daily_return"].dropna()
    ann_ret = ret.mean() * 252
    ann_vol = ret.std() * np.sqrt(252)

    summary = {
        "avg_daily_return_pct":  round(float(ret.mean()) * 100, 4),
        "daily_return_std":      round(float(ret.std()) * 100, 4),
        "annualized_return_pct": round(float(ann_ret) * 100, 2),
        "annualized_volatility": round(float(ann_vol) * 100, 2),
        "sharpe_ratio":          round(float(ann_ret / ann_vol) if ann_vol else 0, 2),
        "skewness":              round(float(ret.skew()), 4),
        "kurtosis":              round(float(ret.kurt()), 4),
        "best_day_pct":         round(float(ret.max()) * 100, 2),
        "worst_day_pct":        round(float(ret.min()) * 100, 2),
        "positive_days_pct":    round(float((ret > 0).mean()) * 100, 2),
    }
    return df, summary
