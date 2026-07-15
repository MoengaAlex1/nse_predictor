import pandas as pd
import numpy as np


def correlation_analysis(stock_data: dict) -> pd.DataFrame:
    returns_df = pd.DataFrame()
    for ticker, df in stock_data.items():
        log_ret = np.log(df["Close"] / df["Close"].shift(1))
        returns_df[ticker] = log_ret
    return returns_df.corr(method="pearson")


def interpret_correlation(corr_matrix: pd.DataFrame) -> list[dict]:
    tickers = corr_matrix.columns.tolist()
    pairs = []
    for i, t1 in enumerate(tickers):
        for t2 in tickers[i+1:]:
            r = round(float(corr_matrix.loc[t1, t2]), 4)
            if abs(r) > 0.7:
                strength = "Strong"
            elif abs(r) > 0.3:
                strength = "Moderate"
            else:
                strength = "Weak"
            direction = "positive" if r >= 0 else "negative"
            pairs.append({
                "pair": f"{t1} / {t2}",
                "correlation": r,
                "strength": strength,
                "direction": direction,
                "portfolio_note": (
                    "High overlap — limited diversification" if abs(r) > 0.7
                    else "Good diversification candidate" if abs(r) < 0.3
                    else "Moderate diversification"
                )
            })
    return sorted(pairs, key=lambda x: abs(x["correlation"]), reverse=True)
