import pandas as pd


def compute_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    for window in [10, 20, 50, 100, 200]:
        df[f"SMA_{window}"] = df["Close"].rolling(window).mean()

    for span in [12, 26, 50]:
        df[f"EMA_{span}"] = df["Close"].ewm(span=span, adjust=False).mean()

    # Golden Cross: SMA_50 crosses above SMA_200 → BUY signal
    df["golden_cross"] = (
        (df["SMA_50"] > df["SMA_200"]) &
        (df["SMA_50"].shift(1) <= df["SMA_200"].shift(1))
    ).astype(int)

    # Death Cross: SMA_50 crosses below SMA_200 → SELL signal
    df["death_cross"] = (
        (df["SMA_50"] < df["SMA_200"]) &
        (df["SMA_50"].shift(1) >= df["SMA_200"].shift(1))
    ).astype(int)

    return df


def latest_ma_summary(df: pd.DataFrame) -> dict:
    last = df.iloc[-1]
    close = last["Close"]
    summary = {}
    for col in ["SMA_10", "SMA_20", "SMA_50", "SMA_100", "SMA_200",
                "EMA_12", "EMA_26", "EMA_50"]:
        if col in df.columns and not pd.isna(last[col]):
            val = round(float(last[col]), 2)
            pct_diff = round((close - val) / val * 100, 2)
            summary[col] = {"value": val, "price_vs_ma_pct": pct_diff}
    return summary
