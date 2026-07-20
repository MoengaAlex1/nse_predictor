"""
Plotly interactive dashboard — saves a self-contained HTML file.
Charts: price+MAs, daily returns histogram, candlestick+Bollinger,
        correlation heatmap, VaR distribution, prediction vs actual,
        Monte Carlo paths, RSI+MACD subplots.
"""
import sys
import io
import logging
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.figure_factory as ff
from plotly.subplots import make_subplots
from pathlib import Path
from config import REPORTS_DIR, MONTE_CARLO_SIMS, MONTE_CARLO_HORIZON, DEFAULT_INVESTMENT

log = logging.getLogger(__name__)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _price_and_ma_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df["Close"], name="Close",
                             line=dict(color="#1f77b4", width=1.5)))
    for ma, color in [("SMA_20", "#ff7f0e"), ("SMA_50", "#2ca02c"), ("SMA_200", "#d62728")]:
        if ma in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[ma], name=ma,
                                     line=dict(dash="dash"), opacity=0.8))
    # Golden / death cross markers
    for col, sym, color, name in [
        ("golden_cross", "triangle-up", "gold", "Golden Cross"),
        ("death_cross",  "triangle-down", "red",  "Death Cross"),
    ]:
        if col in df.columns:
            crosses = df[df[col] == 1]
            fig.add_trace(go.Scatter(x=crosses.index, y=crosses["Close"],
                                     mode="markers", marker=dict(symbol=sym, size=12, color=color),
                                     name=name))
    fig.update_layout(title=f"{ticker} — Price History & Moving Averages",
                      xaxis_title="Date", yaxis_title="Price (KES)",
                      template="plotly_dark", height=500)
    return fig


def _returns_histogram(df: pd.DataFrame, ticker: str) -> go.Figure:
    if "daily_return" not in df.columns:
        df = df.copy()
        df["daily_return"] = df["Close"].pct_change()
    returns = df["daily_return"].dropna() * 100
    fig = ff.create_distplot([returns.values], [f"{ticker} daily returns (%)"],
                             bin_size=0.2, show_rug=False)
    fig.update_layout(title=f"{ticker} — Daily Return Distribution",
                      xaxis_title="Daily Return (%)", template="plotly_dark", height=400)
    return fig


def _candlestick_bollinger(df: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df.index, open=df["Open"], high=df["High"],
                                  low=df["Low"], close=df["Close"], name="OHLC"))
    for band, color, name in [
        ("BB_upper", "rgba(255,127,14,0.4)", "BB Upper"),
        ("BB_lower", "rgba(255,127,14,0.4)", "BB Lower"),
    ]:
        if band in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df[band], name=name,
                                     line=dict(color=color, dash="dot")))
    fig.update_layout(title=f"{ticker} — Candlestick + Bollinger Bands",
                      xaxis_rangeslider_visible=False,
                      template="plotly_dark", height=500)
    return fig


def _correlation_heatmap(corr_matrix: pd.DataFrame) -> go.Figure:
    tickers = corr_matrix.columns.tolist()
    fig = go.Figure(go.Heatmap(
        z=corr_matrix.values,
        x=tickers, y=tickers,
        colorscale="RdBu", zmid=0,
        text=np.round(corr_matrix.values, 2),
        texttemplate="%{text}",
        colorbar=dict(title="Pearson r"),
    ))
    fig.update_layout(title="NSE Stock Correlation Matrix (log-returns)",
                      template="plotly_dark", height=450)
    return fig


def _var_distribution(df: pd.DataFrame, ticker: str,
                      investment: float = DEFAULT_INVESTMENT) -> go.Figure:
    returns = df["Close"].pct_change().dropna()
    mu, sigma = float(returns.mean()), float(returns.std())
    np.random.seed(42)
    sim_returns = np.random.normal(mu, sigma, (MONTE_CARLO_SIMS, MONTE_CARLO_HORIZON))
    final_values = investment * np.prod(1 + sim_returns, axis=1)
    pnl = final_values - investment
    var_95 = float(np.percentile(pnl, 5))

    fig = go.Figure()
    fig.add_trace(go.Histogram(x=pnl, nbinsx=100, name="30-day P&L",
                               marker_color="#1f77b4", opacity=0.7))
    fig.add_vline(x=var_95, line_color="red", line_dash="dash",
                  annotation_text=f"95% VaR: KES {var_95:,.0f}", annotation_position="top right")
    fig.update_layout(title=f"{ticker} — Monte Carlo VaR Distribution (30d, KES {investment:,.0f})",
                      xaxis_title="P&L (KES)", yaxis_title="Simulations",
                      template="plotly_dark", height=400)
    return fig


def _prediction_vs_actual(actual: np.ndarray, predicted: np.ndarray,
                           ticker: str) -> go.Figure:
    idx = list(range(len(actual)))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=idx, y=actual,    name="Actual",    line=dict(color="#1f77b4")))
    fig.add_trace(go.Scatter(x=idx, y=predicted, name="Predicted", line=dict(color="#ff7f0e", dash="dash")))
    fig.update_layout(title=f"{ticker} — Ensemble Prediction vs Actual",
                      xaxis_title="Test Day", yaxis_title="Price (KES)",
                      template="plotly_dark", height=450)
    return fig


def _rsi_macd_chart(df: pd.DataFrame, ticker: str) -> go.Figure:
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        subplot_titles=["RSI (14)", "MACD"])
    if "RSI_14" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["RSI_14"], name="RSI 14",
                                 line=dict(color="#9467bd")), row=1, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="red",   row=1, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=1, col=1)
    if "MACD" in df.columns and "MACD_signal" in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD"],        name="MACD",
                                 line=dict(color="#1f77b4")), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["MACD_signal"], name="Signal",
                                 line=dict(color="#ff7f0e")), row=2, col=1)
    if "MACD_diff" in df.columns:
        fig.add_trace(go.Bar(x=df.index, y=df["MACD_diff"], name="Histogram",
                             marker_color="gray", opacity=0.5), row=2, col=1)
    fig.update_layout(title=f"{ticker} — RSI & MACD Indicators",
                      template="plotly_dark", height=500)
    return fig


def _monte_carlo_paths(df: pd.DataFrame, ticker: str,
                       investment: float = DEFAULT_INVESTMENT,
                       n_paths: int = 200) -> go.Figure:
    returns = df["Close"].pct_change().dropna()
    mu, sigma = float(returns.mean()), float(returns.std())
    np.random.seed(42)
    sim = np.random.normal(mu, sigma, (n_paths, MONTE_CARLO_HORIZON))
    paths = investment * np.cumprod(1 + sim, axis=1)

    fig = go.Figure()
    for i in range(n_paths):
        fig.add_trace(go.Scatter(
            x=list(range(MONTE_CARLO_HORIZON)), y=paths[i],
            mode="lines", line=dict(width=0.5, color="rgba(31,119,180,0.15)"),
            showlegend=False,
        ))
    percentile_5  = np.percentile(paths, 5,  axis=0)
    percentile_95 = np.percentile(paths, 95, axis=0)
    median        = np.percentile(paths, 50, axis=0)
    for y, name, color in [(percentile_5, "5th pct", "red"),
                            (median, "Median", "white"),
                            (percentile_95, "95th pct", "green")]:
        fig.add_trace(go.Scatter(x=list(range(MONTE_CARLO_HORIZON)), y=y,
                                 name=name, line=dict(color=color, width=2)))
    fig.update_layout(title=f"{ticker} — Monte Carlo Price Paths (30d, KES {investment:,.0f})",
                      xaxis_title="Days", yaxis_title="Portfolio Value (KES)",
                      template="plotly_dark", height=450)
    return fig


def build_dashboard(
    df: pd.DataFrame,
    ticker: str,
    corr_matrix: pd.DataFrame = None,
    actual: np.ndarray = None,
    predicted: np.ndarray = None,
    investment: float = DEFAULT_INVESTMENT,
) -> str:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / f"{ticker.replace('.', '_')}_report.html"

    from plotly.io import to_html

    charts = []
    charts.append(_price_and_ma_chart(df, ticker))
    charts.append(_returns_histogram(df, ticker))
    charts.append(_candlestick_bollinger(df, ticker))
    if corr_matrix is not None:
        charts.append(_correlation_heatmap(corr_matrix))
    charts.append(_var_distribution(df, ticker, investment))
    if actual is not None and predicted is not None:
        charts.append(_prediction_vs_actual(actual, predicted, ticker))
    charts.append(_monte_carlo_paths(df, ticker, investment))
    charts.append(_rsi_macd_chart(df, ticker))

    html_parts = [
        "<!DOCTYPE html><html><head>",
        "<meta charset='utf-8'>",
        f"<title>NSE {ticker} Analysis Report</title>",
        "<style>body{{background:#1a1a2e;color:#eee;font-family:sans-serif;padding:20px}}"
        "h1{{color:#00d4ff}} .chart{{margin-bottom:40px}}</style>",
        "</head><body>",
        f"<h1>NSE Stock Report — {ticker}</h1>",
    ]
    include_plotlyjs = True
    for fig in charts:
        html_parts.append(f"<div class='chart'>")
        html_parts.append(to_html(fig, full_html=False, include_plotlyjs=include_plotlyjs))
        html_parts.append("</div>")
        include_plotlyjs = False  # embed JS only once

    html_parts.append("</body></html>")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    log.info("Dashboard saved -> %s", out_path)
    return str(out_path)
