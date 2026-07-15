import numpy as np
import pandas as pd
from scipy.stats import norm
from config import DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE, MONTE_CARLO_SIMS, MONTE_CARLO_HORIZON


def value_at_risk(
    df: pd.DataFrame,
    investment: float = DEFAULT_INVESTMENT,
    confidence: float = DEFAULT_CONFIDENCE,
) -> dict:
    returns = df["Close"].pct_change().dropna()
    mu, sigma = float(returns.mean()), float(returns.std())

    # Historical VaR
    historical_var = float(np.percentile(returns, (1 - confidence) * 100))

    # Parametric VaR (Gaussian)
    parametric_var = float(norm.ppf(1 - confidence, mu, sigma))

    # Monte Carlo VaR (10,000 paths × 30-day horizon)
    np.random.seed(42)
    sim_returns = np.random.normal(mu, sigma, (MONTE_CARLO_SIMS, MONTE_CARLO_HORIZON))
    sim_portfolio = investment * np.prod(1 + sim_returns, axis=1)
    mc_var = float(investment - np.percentile(sim_portfolio, (1 - confidence) * 100))

    conf_pct = int(confidence * 100)
    return {
        "investment_KES":          investment,
        "confidence_level":        f"{conf_pct}%",
        "historical_var_pct":      round(historical_var * 100, 2),
        "historical_var_KES":      round(abs(historical_var) * investment, 2),
        "parametric_var_pct":      round(parametric_var * 100, 2),
        "parametric_var_KES":      round(abs(parametric_var) * investment, 2),
        "monte_carlo_var_30d_KES": round(mc_var, 2),
        "interpretation": (
            f"At {conf_pct}% confidence, you could lose up to "
            f"KES {abs(historical_var) * investment:,.0f} in a single day "
            f"on a KES {investment:,.0f} investment."
        ),
    }


def sharpe_ratio(df: pd.DataFrame, risk_free_rate: float = 0.0) -> float:
    ret = df["Close"].pct_change().dropna()
    ann_ret = ret.mean() * 252 - risk_free_rate
    ann_vol = ret.std() * np.sqrt(252)
    return round(float(ann_ret / ann_vol) if ann_vol else 0.0, 4)
