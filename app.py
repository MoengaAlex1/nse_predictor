"""
NSE Market Dashboard — plain-language stock analysis for everyday investors.
Run:  python app.py   →   open http://127.0.0.1:8050
"""
import sys, io, json, base64, subprocess, tempfile, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash
from dash import dcc, html, Input, Output, State, ctx, dash_table
import dash_bootstrap_components as dbc

from config import (NSE_TICKERS, DATA_CLEANED, DATA_FEATURES, DATA_RAW,
                    DEFAULT_INVESTMENT, DEFAULT_CONFIDENCE, MONTE_CARLO_HORIZON)

# ── Company metadata ─────────────────────────────────────────────────────────
_PALETTE = [
    "#38bdf8","#a78bfa","#f472b6","#fb923c","#34d399","#f59e0b",
    "#60a5fa","#e879f9","#4ade80","#fbbf24","#c084fc","#818cf8",
    "#f87171","#2dd4bf","#facc15","#94a3b8","#06b6d4","#8b5cf6",
    "#ec4899","#84cc16",
]
_SECTOR_ICONS = {
    "Banking": "🏦", "Insurance": "🛡️", "Telecom": "📱",
    "Energy": "⚡", "Manufacturing": "🏭", "Beverages": "🍺",
    "Agriculture": "🌾", "Commercial": "🛒", "Media": "📰",
    "Real Estate": "🏠", "Investment": "💼", "Transport": "✈️",
    "Exchange": "📊",
}
_RAW_COMPANIES = [
    # (ticker_short, name, sector)
    ("ABSA", "ABSA Bank Kenya",              "Banking"),
    ("ALP",  "ALP Industrial REIT",          "Real Estate"),
    ("AMAC", "Africa Mega Agricorp",         "Manufacturing"),
    ("BAT",  "BAT Kenya",                    "Manufacturing"),
    ("BKG",  "BK Group",                     "Banking"),
    ("BOC",  "BOC Kenya",                    "Energy"),
    ("BRIT", "Britam Holdings",              "Insurance"),
    ("CARB", "Carbacid Investments",         "Manufacturing"),
    ("CGEN", "Centum Generation",            "Investment"),
    ("CIC",  "CIC Insurance Group",          "Insurance"),
    ("COOP", "Co-operative Bank",            "Banking"),
    ("CRWN", "Crown Paints Kenya",           "Manufacturing"),
    ("CTUM", "Cavendish Management",         "Manufacturing"),
    ("DTK",  "Diamond Trust Bank",           "Banking"),
    ("EABL", "East African Breweries",       "Beverages"),
    ("EGAD", "East African Portland Cement", "Investment"),
    ("EQTY", "Equity Group Holdings",        "Banking"),
    ("EVRD", "Eveready East Africa",         "Commercial"),
    ("FMLY", "Family Bank",                  "Banking"),
    ("FTGH", "Fahari I-REIT",               "Real Estate"),
    ("GLD",  "Gold Coin Kenya",              "Commercial"),
    ("HAFR", "Home Afrika",                  "Commercial"),
    ("HFCK", "HF Group",                     "Banking"),
    ("IMH",  "I&M Holdings",                 "Banking"),
    ("JUB",  "Jubilee Holdings",             "Insurance"),
    ("KAPC", "KAPS Medical International",   "Commercial"),
    ("KCB",  "KCB Group",                    "Banking"),
    ("KEGN", "KenGen",                       "Energy"),
    ("KNRE", "Kenya Reinsurance",            "Insurance"),
    ("KPC",  "Kenya Power (Ord)",            "Energy"),
    ("KPLC", "Kenya Power (Pref)",           "Energy"),
    ("KQ",   "Kenya Airways",               "Transport"),
    ("KUKZ", "Kakuzi",                       "Agriculture"),
    ("KURV", "Kurwitu Ventures",             "Commercial"),
    ("LBTY", "Liberty Kenya Holdings",       "Insurance"),
    ("LIMT", "Limuru Tea",                   "Agriculture"),
    ("LKL",  "Longhorn Publishers",          "Commercial"),
    ("NBV",  "Nairobi Business Ventures",    "Banking"),
    ("NCBA", "NCBA Group",                   "Banking"),
    ("NMG",  "Nation Media Group",           "Media"),
    ("NSE",  "Nairobi Securities Exchange",  "Exchange"),
    ("OCH",  "Olympia Capital Holdings",     "Commercial"),
    ("PORT", "East African Portland Cement", "Manufacturing"),
    ("SASN", "Sasini",                       "Agriculture"),
    ("SBIC", "SBM Bank Kenya",               "Banking"),
    ("SCAN", "Scangroup",                    "Commercial"),
    ("SCBK", "Standard Chartered Bank Kenya","Banking"),
    ("SCOM", "Safaricom",                    "Telecom"),
    ("SGL",  "Standard Group",               "Media"),
    ("SKL",  "Stanbic Kenya",               "Banking"),
    ("SLAM", "Sanlam Kenya",                 "Insurance"),
    ("SMER", "Sameer Africa",               "Manufacturing"),
    ("SMWF", "Stanlib Fahari REIT",          "Real Estate"),
    ("TOTL", "TotalEnergies EP Kenya",       "Energy"),
    ("TPSE", "TransCentury",                 "Transport"),
    ("TRFC", "TransAfrica",                  "Transport"),
    ("UCHM", "Unga Group Chemicals",         "Manufacturing"),
    ("UMME", "Umme",                         "Investment"),
    ("UNGA", "Unga Group",                   "Manufacturing"),
    ("WTK",  "Williamson Tea Kenya",         "Agriculture"),
    ("XPRS", "Express Kenya",               "Commercial"),
]
# Build COMPANIES — keep the original 5 companies' colors/icons intact
_ORIGINAL_COLORS = {
    "SCOM": "#38bdf8", "EQTY": "#a78bfa",
    "KCB":  "#f472b6", "EABL": "#fb923c", "COOP": "#34d399",
}
COMPANIES = {}
_palette_idx = 0
for _short, _name, _sector in _RAW_COMPANIES:
    _ticker = f"{_short}.NR"
    if _short in _ORIGINAL_COLORS:
        _color = _ORIGINAL_COLORS[_short]
    else:
        _color = _PALETTE[_palette_idx % len(_PALETTE)]
        _palette_idx += 1
    COMPANIES[_ticker] = dict(
        name=_name, short=_short, sector=_sector,
        color=_color, icon=_SECTOR_ICONS.get(_sector, "📈"),
    )
# Override icons for original 5
COMPANIES["SCOM.NR"]["icon"] = "📱"
COMPANIES["EQTY.NR"]["icon"] = "🏦"
COMPANIES["KCB.NR"]["icon"]  = "🏦"
COMPANIES["EABL.NR"]["icon"] = "🍺"
COMPANIES["COOP.NR"]["icon"] = "🏦"

# Auto-derive SECTORS from COMPANIES
_all_sectors = {}
for _tk, _meta in COMPANIES.items():
    _all_sectors.setdefault(_meta["sector"], []).append(_tk)
SECTORS = {"All Companies": list(COMPANIES.keys()), **_all_sectors}

PERIODS = {"1 Month":21,"3 Months":63,"6 Months":126,"1 Year":252,"3 Years":756,"All Time":9999,"Custom Range":0}

# ── Design tokens ────────────────────────────────────────────────────────────
C = dict(bg="#07090f", panel="#0d1117", card="#161b22", border="#21262d",
         accent="#38bdf8", buy="#22c55e", sell="#ef4444", hold="#f59e0b",
         text="#e6edf3", muted="#8b949e", header="#010409")

ADVICE = {
    "BUY":  dict(label="Good time to buy",   color=C["buy"],  bg="#052e16", emoji="↑"),
    "SELL": dict(label="Consider selling",   color=C["sell"], bg="#2d0a0a", emoji="↓"),
    "HOLD": dict(label="Hold what you have", color=C["hold"], bg="#292101", emoji="→"),
}
CHART_BASE = dict(template="plotly_dark", paper_bgcolor=C["card"], plot_bgcolor=C["card"],
                  font=dict(color=C["text"], size=11),
                  margin=dict(l=10, r=10, t=40, b=10),
                  legend=dict(bgcolor="rgba(0,0,0,0)"))

# ── Data helpers ──────────────────────────────────────────────────────────────
def load_df(ticker):
    p = DATA_CLEANED / f"{ticker.replace('.','_')}_cleaned.csv"
    return pd.read_csv(p, index_col="Date", parse_dates=True) if p.exists() else None

def load_sig(ticker):
    p = DATA_FEATURES / f"{ticker.replace('.','_')}_signal.json"
    if not p.exists(): return None
    with open(p) as f: return json.load(f)

def pct_change_over(df, days):
    n = min(days, len(df)-1)
    if n < 1: return 0.0
    return (df["Close"].iloc[-1] - df["Close"].iloc[-1-n]) / df["Close"].iloc[-1-n] * 100

def risk_label(var_pct):
    v = abs(var_pct or 0)
    if v < 5:   return "Low",    C["buy"]
    if v < 10:  return "Medium", C["hold"]
    return "High", C["sell"]

# ── Chart builders ────────────────────────────────────────────────────────────
def chart_price_simple(df, ticker, days=252):
    meta = COMPANIES.get(ticker, {})
    name = meta.get("name", ticker)
    color = meta.get("color", C["accent"])
    sub = df.tail(min(days, len(df)))
    fig = go.Figure()
    # Fill area under price line
    fig.add_trace(go.Scatter(
        x=sub.index, y=sub["Close"], name="Price",
        line=dict(color=color, width=2),
        fill="tozeroy", fillcolor=color.replace(")", ",0.08)").replace("rgb","rgba") if "rgb" in color else f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.08)",
    ))
    # Simple 50-day average line
    if len(sub) > 50:
        avg = sub["Close"].rolling(50).mean()
        fig.add_trace(go.Scatter(x=sub.index, y=avg, name="50-day average",
                                 line=dict(color="#ffffff", width=1, dash="dot"), opacity=0.5))
    fig.update_layout(**CHART_BASE, height=320,
                      title=dict(text=f"{name} — Price History (KES)", font=dict(color=color)),
                      xaxis_title="", yaxis_title="Price (KES)")
    fig.update_xaxes(gridcolor=C["border"], zeroline=False)
    fig.update_yaxes(gridcolor=C["border"], zeroline=False)
    return fig


def chart_returns_bar(df, name, color):
    periods = {"1M":21,"3M":63,"6M":126,"1Y":252,"3Y":756}
    labels, values, colors = [], [], []
    for lbl, d in periods.items():
        if len(df) > d:
            v = pct_change_over(df, d)
            labels.append(lbl); values.append(round(v,2))
            colors.append(C["buy"] if v >= 0 else C["sell"])
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors,
                           text=[f"{v:+.1f}%" for v in values], textposition="outside"))
    fig.update_layout(**CHART_BASE, height=260,
                      title=dict(text=f"{name} — Returns by Period", font=dict(color=color)),
                      yaxis_title="Change (%)", showlegend=False)
    fig.update_xaxes(gridcolor=C["border"]); fig.update_yaxes(gridcolor=C["border"])
    return fig


def _slice(series, days=252, start=None, end=None):
    """Slice a pandas Series by date range or trailing day count."""
    if start and end:
        return series[start:end]
    return series.tail(min(days, len(series)))


def chart_comparison_indexed(tickers, days=252, start=None, end=None):
    fig = go.Figure()
    for t in tickers:
        df = load_df(t)
        if df is None or len(df) < 2: continue
        meta = COMPANIES.get(t, {})
        sub = _slice(df["Close"], days, start, end)
        if sub.empty: continue
        base = sub.iloc[0]
        if base == 0: continue
        indexed = (sub / base * 100).round(2)
        fig.add_trace(go.Scatter(
            x=indexed.index, y=indexed.values,
            name=meta.get("name", t),
            line=dict(color=meta.get("color", C["accent"]), width=2),
        ))
    fig.add_hline(y=100, line_dash="dash", line_color=C["muted"],
                  annotation_text="Starting point", annotation_position="left")
    fig.update_layout(**CHART_BASE, height=400,
                      title=dict(text="How KES 100 invested in each company would have grown",
                                 font=dict(color=C["accent"])),
                      yaxis_title="Value of KES 100 invested",
                      hovermode="x unified")
    fig.update_xaxes(gridcolor=C["border"]); fig.update_yaxes(gridcolor=C["border"])
    return fig


def chart_performance_ranked(days=252, start=None, end=None):
    rows = []
    for t, meta in COMPANIES.items():
        df = load_df(t)
        if df is None: continue
        if start and end:
            sub = df["Close"][start:end]
            if len(sub) < 2: continue
            chg = (sub.iloc[-1] - sub.iloc[0]) / sub.iloc[0] * 100 if sub.iloc[0] else 0.0
        else:
            chg = pct_change_over(df, days)
        rows.append((meta["name"], chg, meta["color"]))
    rows.sort(key=lambda x: x[1])
    names, vals, colors = zip(*rows) if rows else ([], [], [])
    bar_colors = [C["buy"] if v >= 0 else C["sell"] for v in vals]
    fig = go.Figure(go.Bar(
        y=list(names), x=list(vals),
        orientation="h", marker_color=bar_colors,
        text=[f"{v:+.1f}%" for v in vals], textposition="auto",
    ))
    fig.update_layout(**{**CHART_BASE, "margin": dict(l=160, r=10, t=40, b=10)},
                      height=280,
                      title=dict(text="Which company performed best?", font=dict(color=C["accent"])),
                      xaxis_title="Price Change (%)", showlegend=False)
    fig.update_xaxes(gridcolor=C["border"]); fig.update_yaxes(gridcolor=C["border"])
    return fig


def chart_monthly_heatmap(ticker):
    df = load_df(ticker)
    meta = COMPANIES.get(ticker, {})
    if df is None:
        return go.Figure()
    monthly = df["Close"].resample("ME").last().pct_change().dropna() * 100
    monthly.index = pd.to_datetime(monthly.index)
    years  = sorted(monthly.index.year.unique())
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    z = []
    for yr in years:
        row = []
        for m in range(1,13):
            vals = monthly[(monthly.index.year == yr) & (monthly.index.month == m)]
            row.append(round(float(vals.iloc[0]),2) if len(vals) > 0 else None)
        z.append(row)
    fig = go.Figure(go.Heatmap(
        z=z, x=months, y=[str(yr) for yr in years],
        colorscale=[[0,"#7f1d1d"],[0.5,"#1e293b"],[1,"#14532d"]],
        zmid=0,
        text=[[f"{v:+.1f}%" if v is not None else "" for v in row] for row in z],
        texttemplate="%{text}",
        colorbar=dict(title="Monthly\nReturn %"),
    ))
    fig.update_layout(**{**CHART_BASE, "margin": dict(l=50, r=80, t=40, b=10)},
                      height=380,
                      title=dict(text=f"{meta.get('name',ticker)} — Monthly Returns Calendar",
                                 font=dict(color=meta.get("color", C["accent"]))))
    return fig


def chart_all_prices(tickers, days=252, start=None, end=None):
    # Pre-filter to tickers that actually have loaded data
    available = [(t, load_df(t)) for t in tickers]
    available = [(t, df) for t, df in available if df is not None]
    if not available:
        return go.Figure()
    n = len(available)
    spacing = min(0.04, 0.8 / max(n - 1, 1))
    fig = make_subplots(
        rows=n, cols=1, shared_xaxes=True,
        subplot_titles=[COMPANIES.get(t, {}).get("name", t) for t, _ in available],
        vertical_spacing=spacing,
    )
    for i, (t, df) in enumerate(available, 1):
        meta  = COMPANIES.get(t, {})
        sub   = _slice(df["Close"], days, start, end)
        if sub.empty: continue
        color = meta.get("color", C["accent"])
        fig.add_trace(go.Scatter(
            x=sub.index, y=sub.values, name=meta.get("name", t),
            line=dict(color=color, width=1.5),
            fill="tozeroy",
            fillcolor=(lambda c: f"rgba({int(c[1:3],16)},{int(c[3:5],16)},{int(c[5:7],16)},0.09)")(color),
            showlegend=False,
        ), row=i, col=1)
    fig.update_layout(**CHART_BASE, height=max(120 * n + 40, 300),
                      title=dict(text="Price History — All Companies with data (KES)",
                                 font=dict(color=C["accent"])))
    fig.update_xaxes(gridcolor=C["border"], zeroline=False)
    fig.update_yaxes(gridcolor=C["border"], zeroline=False)
    return fig

# ── UI helpers ────────────────────────────────────────────────────────────────
def advice_badge(sig, size="sm"):
    a = ADVICE.get(sig, dict(label=sig or "—", color=C["muted"], bg=C["card"], emoji=""))
    fs = {"sm":"0.68rem","md":"0.9rem","lg":"1.3rem"}.get(size,"0.68rem")
    px = {"sm":"3px 9px","md":"6px 14px","lg":"10px 22px"}.get(size,"3px 9px")
    return html.Span(f"{a['emoji']} {a['label']}", style=dict(
        background=a["bg"], color=a["color"], border=f"1px solid {a['color']}",
        fontWeight=700, fontSize=fs, padding=px, borderRadius="20px",
        letterSpacing="0.02em", whiteSpace="nowrap",
    ))

def stat_pill(label, value, color=None):
    return html.Div([
        html.Div(label, style=dict(fontSize="0.62rem", color=C["muted"],
                                   textTransform="uppercase", letterSpacing="0.07em")),
        html.Div(value, style=dict(fontSize="0.95rem", fontWeight=700,
                                   color=color or C["text"])),
    ], style=dict(background=C["card"], border=f"1px solid {C['border']}",
                  borderRadius="8px", padding="8px 14px", textAlign="center"))

# ── App ───────────────────────────────────────────────────────────────────────
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.CYBORG],
                suppress_callback_exceptions=True)
app.title = "NSE Market Dashboard"

# Tab style helpers
TAB_STYLE = dict(background=C["panel"], color=C["muted"], border="none",
                 padding="10px 20px", fontSize="0.85rem")
TAB_SELECTED = dict(background=C["card"], color=C["accent"],
                    border=f"1px solid {C['border']}", borderBottom="none",
                    padding="10px 20px", fontSize="0.85rem", fontWeight=700)

app.layout = html.Div([
    dcc.Store(id="selected-ticker", data="SCOM.NR"),
    dcc.Store(id="analysis-store", data={}),
    dcc.Store(id="analytics-state", data={"days":252,"sector":"All Companies","heatmap":"SCOM.NR"}),
    dcc.Store(id="overview-view",   data="table"),
    dcc.Store(id="overview-sector", data="All Companies"),
    dcc.Store(id="pipeline-ticker",    data=""),
    dcc.Store(id="pipeline-csv-path",  data=""),
    dcc.Store(id="explorer-data",      data={}),
    dcc.Store(id="explorer-chart-type", data="line"),
    dcc.Download(id="explorer-download-csv"),
    dcc.Download(id="explorer-download-excel"),
    # Interval for polling full-pipeline status (disabled by default)
    dcc.Interval(id="pipeline-poll", interval=3000, n_intervals=0, disabled=True),

    # ── Header ───────────────────────────────────────────────────────────────
    html.Div([
        html.Div([
            html.Span("📈", style=dict(fontSize="1.3rem", marginRight="8px")),
            html.Span("NSE Market Dashboard",
                      style=dict(fontWeight=800, fontSize="1.1rem", color=C["text"])),
            html.Span("Nairobi Securities Exchange · KES",
                      style=dict(fontSize="0.75rem", color=C["muted"], marginLeft="12px")),
        ], style=dict(display="flex", alignItems="center")),
        html.Div([
            dcc.Input(id="search-input", placeholder="🔍  Search company…",
                      debounce=True, style=dict(
                          background=C["card"], border=f"1px solid {C['border']}",
                          color=C["text"], borderRadius="20px",
                          padding="7px 16px", width="230px", fontSize="0.85rem")),
        ], style=dict(display="flex", gap="10px", alignItems="center")),
    ], style=dict(background=C["header"], borderBottom=f"1px solid {C['border']}",
                  padding="12px 24px", display="flex",
                  justifyContent="space-between", alignItems="center")),

    # ── Main tabs ─────────────────────────────────────────────────────────────
    dcc.Tabs(id="main-tabs", value="overview", children=[
        dcc.Tab(label="🏠  Overview",        value="overview",   style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label="🔍  Company",          value="company",    style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label="📊  Analytics",        value="analytics",  style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label="📥  Import & Analyse", value="import_tab", style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label="📅  Data Explorer",   value="explorer",   style=TAB_STYLE, selected_style=TAB_SELECTED),
    ], style=dict(background=C["panel"], borderBottom=f"1px solid {C['border']}")),

    # Permanent overview controls bar — always in DOM, hidden on other tabs
    html.Div([
        html.Div([
            html.Span("Filter: ", style=dict(color=C["muted"], fontSize="0.8rem", marginRight="6px")),
            html.Button("All Companies", id="ov-s-all",  n_clicks=0,
                        style=dict(border=f"1px solid {C['border']}", borderRadius="20px",
                                   padding="5px 16px", cursor="pointer", fontSize="0.8rem",
                                   fontWeight=600, background=C["accent"], color=C["header"])),
            html.Button("Banking",       id="ov-s-banking", n_clicks=0,
                        style=dict(border=f"1px solid {C['border']}", borderRadius="20px",
                                   padding="5px 16px", cursor="pointer", fontSize="0.8rem",
                                   fontWeight=600, background=C["card"], color=C["text"])),
            html.Button("Telecom",       id="ov-s-telecom", n_clicks=0,
                        style=dict(border=f"1px solid {C['border']}", borderRadius="20px",
                                   padding="5px 16px", cursor="pointer", fontSize="0.8rem",
                                   fontWeight=600, background=C["card"], color=C["text"])),
            html.Button("Beverages",     id="ov-s-beverages", n_clicks=0,
                        style=dict(border=f"1px solid {C['border']}", borderRadius="20px",
                                   padding="5px 16px", cursor="pointer", fontSize="0.8rem",
                                   fontWeight=600, background=C["card"], color=C["text"])),
        ], style=dict(display="flex", alignItems="center", flexWrap="wrap", gap="4px")),
        html.Div([
            html.Button("☰  Table", id="ov-v-table", n_clicks=0,
                        style=dict(border=f"1px solid {C['border']}", borderRadius="20px",
                                   padding="5px 16px", cursor="pointer", fontSize="0.8rem",
                                   fontWeight=600, background=C["accent"], color=C["header"])),
            html.Button("⬛  Board", id="ov-v-board", n_clicks=0,
                        style=dict(border=f"1px solid {C['border']}", borderRadius="20px",
                                   padding="5px 16px", cursor="pointer", fontSize="0.8rem",
                                   fontWeight=600, background=C["card"], color=C["muted"])),
        ], style=dict(display="flex", gap="6px")),
    ], id="overview-controls-bar",
       style=dict(display="none", justifyContent="space-between", alignItems="center",
                  padding="10px 24px", borderBottom=f"1px solid {C['border']}")),

    dcc.Loading(html.Div(id="tab-content"), type="dot", color=C["accent"]),

], style=dict(background=C["bg"], color=C["text"], minHeight="100vh",
              fontFamily="'Inter','Segoe UI',sans-serif", margin=0, padding=0))

# ── Tab content router ────────────────────────────────────────────────────────
@app.callback(Output("tab-content","children"),
              Input("main-tabs","value"),
              Input("selected-ticker","data"),
              State("overview-sector","data"),
              State("overview-view","data"),
              State("analysis-store","data"),
              State("analytics-state","data"))
def render_tab(tab, ticker, ov_sector, ov_view, store, astate):
    astate    = astate or {"days":252,"sector":"All Companies","heatmap":"SCOM.NR"}
    ov_sector = ov_sector or "All Companies"
    ov_view   = ov_view   or "table"
    if tab == "overview":
        return html.Div(id="overview-body",
                        children=_build_overview_content(ov_sector, ov_view))
    if tab == "company":    return build_company(ticker, store or {})
    if tab == "analytics":  return build_analytics(
        astate["days"], astate["sector"], astate.get("heatmap","SCOM.NR"),
        astate.get("custom_start"), astate.get("custom_end"))
    if tab == "import_tab": return build_import_tab()
    if tab == "explorer":   return build_explorer_tab()
    return html.Div()


# ── Overview controls bar: show/hide based on active tab ─────────────────────
@app.callback(
    Output("overview-controls-bar","style"),
    Input("main-tabs","value"),
)
def toggle_controls_bar(tab):
    vis = dict(display="flex", justifyContent="space-between", alignItems="center",
               padding="10px 24px", borderBottom=f"1px solid {C['border']}")
    return vis if tab == "overview" else dict(display="none")


# ── Overview sector filter (fixed IDs — no pattern matching) ─────────────────
@app.callback(
    Output("overview-sector","data"),
    Input("ov-s-all","n_clicks"),
    Input("ov-s-banking","n_clicks"),
    Input("ov-s-telecom","n_clicks"),
    Input("ov-s-beverages","n_clicks"),
    prevent_initial_call=True,
)
def set_ov_sector(n_all, n_bk, n_tel, n_bev):
    sector_map = {
        "ov-s-all":      "All Companies",
        "ov-s-banking":  "Banking",
        "ov-s-telecom":  "Telecom",
        "ov-s-beverages":"Beverages",
    }
    return sector_map.get(ctx.triggered_id, "All Companies")


# ── Overview view toggle (fixed IDs) ─────────────────────────────────────────
@app.callback(
    Output("overview-view","data"),
    Input("ov-v-table","n_clicks"),
    Input("ov-v-board","n_clicks"),
    prevent_initial_call=True,
)
def set_ov_view(n_table, n_board):
    return "board" if ctx.triggered_id == "ov-v-board" else "table"


# ── Update overview body when sector or view changes ─────────────────────────
@app.callback(
    Output("overview-body","children"),
    Input("overview-sector","data"),
    Input("overview-view","data"),
    prevent_initial_call=True,
)
def update_overview_body(sector, view):
    return _build_overview_content(sector or "All Companies", view or "table")


# ── Highlight active sector button ───────────────────────────────────────────
_btn_base = dict(border=f"1px solid {C['border']}", borderRadius="20px",
                 padding="5px 16px", cursor="pointer", fontSize="0.8rem", fontWeight=600)

@app.callback(
    Output("ov-s-all","style"),
    Output("ov-s-banking","style"),
    Output("ov-s-telecom","style"),
    Output("ov-s-beverages","style"),
    Input("overview-sector","data"),
)
def update_sector_btn_styles(sector):
    sector = sector or "All Companies"
    keys = ["All Companies","Banking","Telecom","Beverages"]
    return [dict(**_btn_base,
                 background=C["accent"] if s==sector else C["card"],
                 color=C["header"]      if s==sector else C["text"])
            for s in keys]


# ── Highlight active view button ─────────────────────────────────────────────
@app.callback(
    Output("ov-v-table","style"),
    Output("ov-v-board","style"),
    Input("overview-view","data"),
)
def update_view_btn_styles(view):
    view = view or "table"
    return [
        dict(**_btn_base, background=C["accent"] if view=="table" else C["card"],
             color=C["header"] if view=="table" else C["muted"]),
        dict(**_btn_base, background=C["accent"] if view=="board" else C["card"],
             color=C["header"] if view=="board" else C["muted"]),
    ]

@app.callback(
    Output("analytics-custom-range-section", "style"),
    Input("analytics-period", "value"),
    prevent_initial_call=True,
)
def toggle_custom_range(period):
    visible = dict(display="flex", gap="14px", alignItems="flex-start", flexWrap="wrap",
                   marginTop="10px", padding="10px 24px",
                   borderTop=f"1px solid {C['border']}")
    hidden  = dict(display="none")
    return visible if period == 0 else hidden


@app.callback(
    Output("analytics-state","data"),
    Input("analytics-period","value"),
    Input("analytics-sector","value"),
    Input("heatmap-ticker","value"),
    Input("analytics-apply-range","n_clicks"),
    State("analytics-custom-start","date"),
    State("analytics-custom-end","date"),
    State("analytics-state","data"),
    prevent_initial_call=True,
)
def update_analytics_state(period, sector, heatmap, n_apply, custom_start, custom_end, state):
    state = state or {"days":252,"sector":"All Companies","heatmap":"SCOM.NR","custom_start":None,"custom_end":None}
    triggered = ctx.triggered_id
    if triggered == "analytics-apply-range" and custom_start and custom_end:
        return {**state, "days":0, "sector":sector or state["sector"],
                "heatmap":heatmap or state["heatmap"],
                "custom_start":custom_start, "custom_end":custom_end}
    if triggered != "analytics-apply-range":
        return {**state,
                "days":period if period is not None else state["days"],
                "sector":sector or state["sector"],
                "heatmap":heatmap or state["heatmap"]}
    return state

# ── TAB 1: OVERVIEW — Today's Signal Board ────────────────────────────────────
def _build_overview_content(sector="All Companies", view="table"):
    # Gather data for signal table — filtered by sector
    filtered_tickers = SECTORS.get(sector, NSE_TICKERS)
    rows = []
    buy_count = sell_count = hold_count = 0
    for t in filtered_tickers:
        meta = COMPANIES.get(t, {})
        df   = load_df(t)
        sig  = load_sig(t)
        if df is None:
            continue
        last  = float(df["Close"].iloc[-1])
        prev  = float(df["Close"].iloc[-2]) if len(df) > 1 else last
        chg   = (last - prev) / prev * 100 if prev else 0.0
        chg1y = pct_change_over(df, 252)
        ra    = sig.get("risk_adjusted_signal", "—") if sig else "—"
        rlabel, _ = risk_label(sig.get("var_95_pct", 0) if sig else 0)

        if ra == "BUY":  buy_count  += 1
        elif ra == "SELL": sell_count += 1
        elif ra == "HOLD": hold_count += 1

        rows.append({
            "_ticker": t,
            "Company":        meta.get("name", t),
            "Sector":         meta.get("sector", "—"),
            "Price (KES)":    f"{last:,.2f}",
            "Today's Change": f"{chg:+.2f}%",
            "1-Year Change":  f"{chg1y:+.1f}%",
            "AI Advice":      ra,
            "Risk Level":     rlabel,
        })

    # Counter badges
    counter_style = lambda bg, border: dict(
        background=bg, border=f"1px solid {border}",
        borderRadius="12px", padding="16px 28px", textAlign="center",
        minWidth="120px",
    )
    counters = html.Div([
        html.Div([
            html.Div(str(buy_count),  style=dict(fontSize="2rem", fontWeight=800, color=C["buy"])),
            html.Div("BUY signals",   style=dict(fontSize="0.72rem", color=C["muted"], marginTop="2px")),
        ], style=counter_style("#052e1680", C["buy"])),
        html.Div([
            html.Div(str(hold_count), style=dict(fontSize="2rem", fontWeight=800, color=C["hold"])),
            html.Div("HOLD signals",  style=dict(fontSize="0.72rem", color=C["muted"], marginTop="2px")),
        ], style=counter_style("#29210180", C["hold"])),
        html.Div([
            html.Div(str(sell_count), style=dict(fontSize="2rem", fontWeight=800, color=C["sell"])),
            html.Div("SELL signals",  style=dict(fontSize="0.72rem", color=C["muted"], marginTop="2px")),
        ], style=counter_style("#2d0a0a80", C["sell"])),
    ], style=dict(display="flex", gap="16px", flexWrap="wrap",
                  padding="16px 24px", borderBottom=f"1px solid {C['border']}"))

    # ── Board view (Kanban columns: BUY | HOLD | SELL) ────────────────────────
    def company_mini_card(r):
        adv = r["AI Advice"]
        meta = COMPANIES.get(r["_ticker"], {})
        adv_color, adv_bg = {
            "BUY":  (C["buy"],  "#052e16"),
            "SELL": (C["sell"], "#2d0a0a"),
            "HOLD": (C["hold"], "#292101"),
        }.get(adv, (C["muted"], C["card"]))
        chg_val = r["Today's Change"]
        chg_c = C["buy"] if "+" in chg_val and chg_val != "+0.00%" else C["sell"] if "-" in chg_val else C["muted"]
        return html.Div([
            html.Div([
                html.Span(meta.get("icon",""), style=dict(fontSize="1.1rem")),
                html.Div([
                    html.Div(r["Company"], style=dict(fontWeight=700, fontSize="0.85rem", color=C["text"])),
                    html.Span(r["Sector"], style=dict(fontSize="0.63rem", color=meta.get("color",C["accent"]),
                                                       background=meta.get("color","#fff")+"22",
                                                       padding="1px 7px", borderRadius="10px")),
                ]),
            ], style=dict(display="flex", alignItems="center", gap="8px", marginBottom="10px")),
            html.Div([
                html.Span(f"KES {r['Price (KES)']}", style=dict(fontWeight=800, fontSize="0.95rem", color=C["text"])),
                html.Span(f" {chg_val}", style=dict(color=chg_c, fontSize="0.78rem", fontWeight=600)),
            ], style=dict(marginBottom="4px")),
            html.Div(f"1Y: {r['1-Year Change']}  ·  Risk: {r['Risk Level']}",
                     style=dict(fontSize="0.7rem", color=C["muted"])),
        ], id={"type":"overview-row","index":r["_ticker"]}, n_clicks=0,
           style=dict(background=C["card"], border=f"1px solid {adv_bg}",
                      borderRadius="10px", padding="12px", cursor="pointer",
                      marginBottom="10px", transition="border 0.15s"))

    def kanban_col(title, signal, col_color, col_bg, col_rows):
        cards = [company_mini_card(r) for r in col_rows if r["AI Advice"] == signal]
        empty = html.Div("No companies here", style=dict(color=C["muted"], fontSize="0.8rem",
                                                          fontStyle="italic", textAlign="center",
                                                          padding="20px")) if not cards else None
        return html.Div([
            html.Div([
                html.Span(f"{'↑' if signal=='BUY' else '↓' if signal=='SELL' else '→'}  {signal}",
                          style=dict(fontWeight=800, fontSize="0.88rem", color=col_color)),
                html.Span(str(len(cards)),
                          style=dict(background=col_bg, color=col_color, border=f"1px solid {col_color}",
                                     borderRadius="12px", padding="1px 9px", fontSize="0.75rem",
                                     fontWeight=700, marginLeft="8px")),
            ], style=dict(display="flex", alignItems="center",
                          marginBottom="14px", paddingBottom="10px",
                          borderBottom=f"1px solid {col_color}40")),
            html.Div(cards if cards else [empty]),
        ], style=dict(flex="1", background=C["panel"], border=f"1px solid {col_color}30",
                      borderRadius="12px", padding="16px", minWidth="220px"))

    board_view = html.Div([
        kanban_col("Good time to buy",   "BUY",  C["buy"],  "#052e16", rows),
        kanban_col("Hold what you have", "HOLD", C["hold"], "#292101", rows),
        kanban_col("Consider selling",   "SELL", C["sell"], "#2d0a0a", rows),
    ], id="overview-board-view",
       style=dict(display="flex" if view=="board" else "none",
                  gap="16px", padding="16px 24px 24px", flexWrap="wrap"))

    # ── Signal table rows (manual HTML — dash_table doesn't support clickable cell content easily) ──
    def signal_color(sig_val):
        return {
            "BUY":  (C["buy"],  "#052e16"),
            "SELL": (C["sell"], "#2d0a0a"),
            "HOLD": (C["hold"], "#292101"),
        }.get(sig_val, (C["muted"], C["card"]))

    def chg_color(chg_str):
        try:
            v = float(chg_str.replace("%","").replace("+",""))
            return C["buy"] if v >= 0 else C["sell"]
        except Exception:
            return C["muted"]

    th_style = dict(
        padding="10px 14px", fontSize="0.72rem", color=C["muted"],
        fontWeight=700, textTransform="uppercase", letterSpacing="0.07em",
        borderBottom=f"2px solid {C['border']}", textAlign="left",
        background=C["panel"],
    )
    td_style = dict(
        padding="10px 14px", fontSize="0.83rem", color=C["text"],
        borderBottom=f"1px solid {C['border']}",
    )

    header_row = html.Tr([
        html.Th("Company",        style=th_style),
        html.Th("Sector",         style=th_style),
        html.Th("Price (KES)",    style={**th_style, "textAlign":"right"}),
        html.Th("Today's Change", style={**th_style, "textAlign":"right"}),
        html.Th("1-Year Change",  style={**th_style, "textAlign":"right"}),
        html.Th("AI Advice",      style={**th_style, "textAlign":"center"}),
        html.Th("Risk Level",     style={**th_style, "textAlign":"center"}),
    ])

    table_rows = []
    for r in rows:
        t = r["_ticker"]
        adv_color, adv_bg = signal_color(r["AI Advice"])
        risk_col = {
            "Low":    C["buy"],
            "Medium": C["hold"],
            "High":   C["sell"],
        }.get(r["Risk Level"], C["muted"])

        table_rows.append(html.Tr([
            # Clickable company name
            html.Td(
                html.Span(r["Company"], id={"type":"overview-row","index":t},
                          n_clicks=0, style=dict(
                              color=C["accent"], cursor="pointer", fontWeight=600,
                              textDecoration="underline", fontSize="0.85rem",
                          )),
                style=td_style,
            ),
            html.Td(r["Sector"],        style=td_style),
            html.Td(r["Price (KES)"],   style={**td_style, "textAlign":"right", "fontVariantNumeric":"tabular-nums"}),
            html.Td(r["Today's Change"],style={**td_style, "textAlign":"right",
                                              "color": chg_color(r["Today's Change"]),
                                              "fontWeight":600}),
            html.Td(r["1-Year Change"], style={**td_style, "textAlign":"right",
                                              "color": chg_color(r["1-Year Change"]),
                                              "fontWeight":600}),
            html.Td(
                html.Span(f"{ADVICE.get(r['AI Advice'],{}).get('emoji','')} {r['AI Advice']}",
                          style=dict(background=adv_bg, color=adv_color,
                                     border=f"1px solid {adv_color}",
                                     padding="3px 10px", borderRadius="20px",
                                     fontSize="0.72rem", fontWeight=700,
                                     whiteSpace="nowrap")),
                style={**td_style, "textAlign":"center"},
            ),
            html.Td(
                html.Span(r["Risk Level"], style=dict(color=risk_col, fontWeight=700)),
                style={**td_style, "textAlign":"center"},
            ),
        ], style=dict(transition="background 0.12s"), className="overview-row"))

    signal_table = html.Div([
        html.Table(
            [html.Thead(header_row), html.Tbody(table_rows)],
            style=dict(width="100%", borderCollapse="collapse"),
        )
    ], style=dict(overflowX="auto",
                  border=f"1px solid {C['border']}", borderRadius="10px",
                  background=C["card"]))

    hint = html.Div(
        "Click any company name to see full details on the Company tab.",
        style=dict(fontSize="0.78rem", color=C["muted"], fontStyle="italic",
                   marginTop="8px", textAlign="right"),
    )

    return html.Div([
        # intro banner
        html.Div([
            html.Div("Today's Signal Board", style=dict(
                fontSize="1.3rem", fontWeight=800, color=C["text"], marginBottom="4px")),
            html.Div("What should I do today across all my investments? Our AI gives you a simple signal for every company.",
                     style=dict(fontSize="0.85rem", color=C["muted"])),
        ], style=dict(padding="20px 24px 12px", borderBottom=f"1px solid {C['border']}")),

        # BUY / HOLD / SELL counters
        counters,

        # Table view (hidden when board is active)
        html.Div([
            signal_table,
            hint,
        ], id="overview-table-view",
           style=dict(padding="16px 24px 24px",
                      display="none" if view=="board" else "block")),

        # Board view (hidden when table is active)
        board_view,

        # Legend
        html.Div([
            html.Div("How to read the signals:", style=dict(
                fontWeight=700, color=C["text"], marginBottom="8px", fontSize="0.85rem")),
            html.Div([
                html.Div([advice_badge("BUY","sm"),
                          html.Span(" — Our AI thinks the stock price will rise. Could be a good time to invest.",
                                    style=dict(color=C["muted"], fontSize="0.8rem"))],
                         style=dict(display="flex", alignItems="center", gap="8px", marginBottom="6px")),
                html.Div([advice_badge("SELL","sm"),
                          html.Span(" — Our AI thinks the price may fall. Consider reducing your position.",
                                    style=dict(color=C["muted"], fontSize="0.8rem"))],
                         style=dict(display="flex", alignItems="center", gap="8px", marginBottom="6px")),
                html.Div([advice_badge("HOLD","sm"),
                          html.Span(" — The AI is not confident enough to recommend buying or selling right now.",
                                    style=dict(color=C["muted"], fontSize="0.8rem"))],
                         style=dict(display="flex", alignItems="center", gap="8px")),
            ]),
        ], style=dict(margin="0 24px 24px", background=C["card"],
                      border=f"1px solid {C['border']}", borderRadius="10px",
                      padding="16px")),
    ], style=dict(overflowY="auto", maxHeight="calc(100vh - 105px)"))


# ── Callbacks for overview clickable rows ────────────────────────────────────
@app.callback(
    Output("selected-ticker","data"),
    Output("main-tabs","value"),
    Input({"type":"overview-row","index":dash.ALL},"n_clicks"),
    Input({"type":"sidebar-ticker","index":dash.ALL},"n_clicks"),
    Input("search-input","value"),
    State("selected-ticker","data"),
    State("main-tabs","value"),
    prevent_initial_call=True,
)
def select_ticker_and_navigate(overview_clicks, sidebar_clicks, search, current_ticker, current_tab):
    t = ctx.triggered_id
    if isinstance(t, dict):
        new_ticker = t["index"]
        if t.get("type") == "overview-row":
            return new_ticker, "company"
        else:
            # sidebar click — stay on company tab
            return new_ticker, "company"
    if t == "search-input" and search:
        s = search.strip().upper()
        tk = s if s.endswith(".NR") else s + ".NR"
        return tk, "company"
    return current_ticker, current_tab


# ── TAB 2: COMPANY — Deep Dive ────────────────────────────────────────────────
def build_company(ticker, store):
    # Sidebar
    sidebar_items = []
    for t, meta in COMPANIES.items():
        df  = load_df(t)
        sig = load_sig(t)
        last = float(df["Close"].iloc[-1]) if df is not None else 0
        prev = float(df["Close"].iloc[-2]) if df is not None and len(df)>1 else last
        chg  = (last-prev)/prev*100 if prev else 0
        ra   = sig.get("risk_adjusted_signal","—") if sig else "—"
        a    = ADVICE.get(ra, dict(color=C["muted"], bg=C["card"]))
        is_active = t == ticker
        sidebar_items.append(html.Div([
            html.Div(meta["icon"], style=dict(fontSize="1.1rem", width="28px", textAlign="center")),
            html.Div([
                html.Div(meta["name"], style=dict(fontSize="0.82rem", fontWeight=600,
                                                  color=C["accent"] if is_active else C["text"])),
                html.Div(f"KES {last:,.2f}  {chg:+.1f}%",
                         style=dict(fontSize="0.7rem",
                                    color=C["buy"] if chg>=0 else C["sell"])),
            ], style=dict(flex=1)),
            html.Span(f"{ADVICE.get(ra,{}).get('emoji','')} {ra}",
                      style=dict(fontSize="0.65rem", fontWeight=700, color=a["color"],
                                 background=a["bg"], border=f"1px solid {a['color']}",
                                 padding="2px 7px", borderRadius="10px")),
        ], id={"type":"sidebar-ticker","index":t}, n_clicks=0,
           style=dict(display="flex", alignItems="center", gap="8px",
                      padding="10px 14px", cursor="pointer",
                      background="#1c2333" if is_active else "transparent",
                      borderBottom=f"1px solid {C['border']}")))

    sidebar = html.Div([
        html.Div("Companies", style=dict(fontSize="0.65rem", fontWeight=700, color=C["muted"],
                                         letterSpacing="0.1em", padding="10px 14px",
                                         borderBottom=f"1px solid {C['border']}")),
        html.Div(sidebar_items),
    ], style=dict(width="260px", minWidth="260px", background=C["panel"],
                  borderRight=f"1px solid {C['border']}", overflowY="auto"))

    # Main content
    meta = COMPANIES.get(ticker, {})
    df   = load_df(ticker)
    sig  = store.get(ticker) or load_sig(ticker)

    if df is None:
        main = html.Div("No data available for this company.",
                        style=dict(color=C["muted"], padding="40px"))
    else:
        last  = float(df["Close"].iloc[-1])
        prev  = float(df["Close"].iloc[-2]) if len(df)>1 else last
        chg   = (last-prev)/prev*100
        chg_c = C["buy"] if chg>=0 else C["sell"]

        ra_sig = sig.get("risk_adjusted_signal","—") if sig else "—"
        signal = sig.get("signal","—") if sig else "—"
        pred   = sig.get("predicted_price_KES",0) if sig else 0
        pred_c = sig.get("predicted_change_pct",0) if sig else 0
        var_p  = sig.get("var_95_pct",0) if sig else 0
        acc    = sig["metrics"]["directional_accuracy"] if sig and sig.get("metrics") else None
        rlabel, rcolor = risk_label(var_p)
        worst_kes = abs(var_p/100) * DEFAULT_INVESTMENT

        main_children = [
            # Company title
            html.Div([
                html.Span(meta.get("icon",""), style=dict(fontSize="2rem", marginRight="12px")),
                html.Div([
                    html.Div(meta.get("name", ticker),
                             style=dict(fontSize="1.4rem", fontWeight=800, color=C["text"])),
                    html.Span(meta.get("sector",""), style=dict(
                        fontSize="0.7rem", color=meta.get("color",C["accent"]),
                        background=meta.get("color","#fff")+"22",
                        padding="2px 8px", borderRadius="10px")),
                ]),
            ], style=dict(display="flex", alignItems="center",
                          padding="20px 24px 12px")),

            # Price strip
            html.Div([
                html.Div([
                    html.Span(f"KES {last:,.2f}",
                              style=dict(fontSize="2rem", fontWeight=800, color=C["text"])),
                    html.Span(f"  {chg:+.2f}% today",
                              style=dict(color=chg_c, fontSize="1rem", fontWeight=600)),
                ]),
                html.Div(f"52-week range:  KES {df['Close'].tail(252).min():,.2f} – KES {df['Close'].tail(252).max():,.2f}",
                         style=dict(fontSize="0.78rem", color=C["muted"], marginTop="4px")),
            ], style=dict(padding="0 24px 16px",
                          borderBottom=f"1px solid {C['border']}")),

            # Recommendation section
            html.Div([
                html.Div("🤖  What our AI recommends", style=dict(
                    fontWeight=700, fontSize="1rem", color=C["text"], marginBottom="16px")),
                html.Div([
                    # Big advice badge
                    html.Div([
                        html.Div("Our Advice", style=dict(fontSize="0.65rem", color=C["muted"],
                                                          marginBottom="6px", letterSpacing="0.08em")),
                        advice_badge(ra_sig, "lg"),
                        html.Div(ADVICE.get(ra_sig,{}).get("label",""), style=dict(
                            fontSize="0.75rem", color=C["muted"], marginTop="6px")),
                    ], style=dict(textAlign="center", padding="16px",
                                  background=C["card"], borderRadius="10px",
                                  border=f"1px solid {ADVICE.get(ra_sig,{}).get('color',C['border'])}")),

                    # AI reasoning in plain English
                    html.Div([
                        html.Div("Why?", style=dict(fontWeight=700, color=C["text"],
                                                     fontSize="0.85rem", marginBottom="8px")),
                        html.Div([
                            html.Span("📌 ", style=dict(fontSize="0.9rem")),
                            html.Span(
                                f"Our AI predicts the price will move from "
                                f"KES {last:,.2f} to about KES {pred:,.2f} "
                                f"({'rising' if pred_c>0 else 'falling'} by {abs(pred_c):.1f}%).",
                                style=dict(fontSize="0.83rem", color=C["muted"])),
                        ], style=dict(marginBottom="8px")),
                        html.Div([
                            html.Span("⚠️ " if rlabel=="High" else "✅ ", style=dict(fontSize="0.9rem")),
                            html.Span(
                                f"Risk level: {rlabel}. If you invest KES 100,000 in {meta.get('name','this company')}, "
                                f"on a bad day you could lose up to KES {worst_kes:,.0f}.",
                                style=dict(fontSize="0.83rem", color=C["muted"])),
                        ], style=dict(marginBottom="8px")),
                        html.Div([
                            html.Span("🎯 ", style=dict(fontSize="0.9rem")),
                            html.Span(
                                f"Our AI has correctly predicted price direction "
                                f"{acc:.0f} out of every 100 times." if acc else
                                "Run an analysis to see AI accuracy.",
                                style=dict(fontSize="0.83rem", color=C["muted"])),
                        ]),
                    ], style=dict(background=C["card"], borderRadius="10px",
                                  padding="14px", border=f"1px solid {C['border']}")),

                    # Key numbers
                    html.Div([
                        stat_pill("Today's Price",    f"KES {last:,.2f}"),
                        stat_pill("AI Price Target",  f"KES {pred:,.2f}", C["accent"]),
                        stat_pill("Predicted Change", f"{pred_c:+.1f}%",
                                  C["buy"] if pred_c>0 else C["sell"]),
                        stat_pill("Risk Level",       rlabel, rcolor),
                        stat_pill("AI Accuracy",      f"{acc:.0f}%" if acc else "—", C["accent"]),
                        stat_pill("1-Year Change",    f"{pct_change_over(df,252):+.1f}%",
                                  C["buy"] if pct_change_over(df,252)>=0 else C["sell"]),
                    ], style=dict(display="flex", gap="8px", flexWrap="wrap")),

                ], style=dict(display="flex", flexDirection="column", gap="14px")),

                html.Div([
                    html.Button("🔄 Update Analysis", id="quick-btn", style=dict(
                        background=C["accent"], color=C["header"], fontWeight=700,
                        border="none", borderRadius="20px", padding="7px 20px",
                        cursor="pointer", fontSize="0.83rem", marginTop="14px")),
                    dcc.Loading(html.Span(id="quick-status"), type="circle", color=C["accent"]),
                ], style=dict(display="flex", alignItems="center", gap="12px")),

            ], style=dict(padding="20px 24px",
                          borderBottom=f"1px solid {C['border']}")),

            # Price chart with period selector
            html.Div([
                html.Div([
                    html.Span("📈 Price History", style=dict(fontWeight=700, fontSize="0.9rem")),
                    dcc.Dropdown(
                        id="price-period",
                        options=[{"label":k,"value":v} for k,v in PERIODS.items()],
                        value=252,
                        clearable=False,
                        style=dict(background=C["card"], color=C["text"],
                                   border=f"1px solid {C['border']}", width="140px",
                                   fontSize="0.8rem"),
                    ),
                ], style=dict(display="flex", justifyContent="space-between",
                              alignItems="center", marginBottom="8px")),
                dcc.Graph(id="price-chart-company",
                          figure=chart_price_simple(df, ticker),
                          config=dict(displayModeBar=False, scrollZoom=True)),
            ], style=dict(padding="16px 24px", borderBottom=f"1px solid {C['border']}")),

            # Returns bar
            html.Div([
                html.Div("📅 How has the price changed?",
                         style=dict(fontWeight=700, fontSize="0.9rem", marginBottom="8px")),
                dcc.Graph(figure=chart_returns_bar(df, meta.get("name",ticker),
                                                   meta.get("color",C["accent"])),
                          config=dict(displayModeBar=False)),
            ], style=dict(padding="16px 24px")),
        ]
        main = html.Div(main_children, style=dict(flex=1, overflowY="auto"))

    return html.Div([sidebar, main],
                    style=dict(display="flex", flex=1, overflow="hidden",
                               minHeight="calc(100vh - 105px)"))


# ── TAB 3: ANALYTICS — Historical Data Explorer ───────────────────────────────
def build_analytics(days=252, sector="All Companies", heatmap_ticker="SCOM.NR", custom_start=None, custom_end=None):
    tickers = SECTORS.get(sector, NSE_TICKERS)

    # Performance summary table (pre-populated inline)
    rows = []
    for t in NSE_TICKERS:
        df  = load_df(t)
        sig = load_sig(t)
        meta = COMPANIES.get(t, {})
        if df is None: continue
        last = float(df["Close"].iloc[-1])
        rows.append({
            "Company":      meta.get("name", t),
            "Sector":       meta.get("sector", "—"),
            "Price (KES)":  f"{last:,.2f}",
            "1 Month":      f"{pct_change_over(df,21):+.1f}%",
            "3 Months":     f"{pct_change_over(df,63):+.1f}%",
            "6 Months":     f"{pct_change_over(df,126):+.1f}%",
            "1 Year":       f"{pct_change_over(df,252):+.1f}%",
            "All Time":     f"{pct_change_over(df,9999):+.1f}%",
            "AI Advice":    (sig.get("risk_adjusted_signal","—") if sig else "—"),
        })
    if rows:
        df_tbl = pd.DataFrame(rows)
        summary_tbl = dash_table.DataTable(
            data=df_tbl.to_dict("records"),
            columns=[{"name":c,"id":c} for c in df_tbl.columns],
            style_table=dict(overflowX="auto"),
            style_header=dict(background=C["panel"], color=C["muted"],
                              fontWeight=700, fontSize="0.75rem",
                              border=f"1px solid {C['border']}"),
            style_cell=dict(background=C["card"], color=C["text"],
                            fontSize="0.82rem", padding="8px 12px",
                            border=f"1px solid {C['border']}"),
            style_data_conditional=[
                {"if":{"filter_query":"{AI Advice} = BUY"},  "color":C["buy"],  "fontWeight":700},
                {"if":{"filter_query":"{AI Advice} = SELL"}, "color":C["sell"], "fontWeight":700},
                {"if":{"filter_query":"{AI Advice} = HOLD"}, "color":C["hold"], "fontWeight":700},
            ],
        )
    else:
        summary_tbl = html.Div("No data available.", style=dict(color=C["muted"]))

    return html.Div([
        html.Div([
            html.Div("📊  Historical Data Explorer",
                     style=dict(fontSize="1.15rem", fontWeight=800, color=C["text"])),
            html.Div("How have these stocks performed historically? Compare growth, returns, and monthly patterns.",
                     style=dict(fontSize="0.83rem", color=C["muted"], marginTop="2px")),
        ], style=dict(padding="18px 24px 10px")),

        # Controls row
        html.Div([
            html.Div([
                html.Label("Period:", style=dict(color=C["muted"], fontSize="0.8rem",
                                                  marginBottom="4px")),
                dcc.Dropdown(id="analytics-period",
                             options=[{"label":k,"value":v} for k,v in PERIODS.items()],
                             value=days, clearable=False,
                             style=dict(background=C["card"], width="160px", fontSize="0.82rem")),
            ]),
            html.Div([
                html.Label("Sector:", style=dict(color=C["muted"], fontSize="0.8rem",
                                                 marginBottom="4px")),
                dcc.Dropdown(id="analytics-sector",
                             options=[{"label":k,"value":k} for k in SECTORS],
                             value=sector, clearable=False,
                             style=dict(background=C["card"], width="180px", fontSize="0.82rem")),
            ]),
            html.Div([
                html.Label("Calendar view:", style=dict(color=C["muted"], fontSize="0.8rem",
                                                         marginBottom="4px")),
                dcc.Dropdown(id="heatmap-ticker",
                             options=[{"label":f"{v['short']} — {v['name']}","value":k} for k,v in sorted(COMPANIES.items(), key=lambda x: x[1]['name'])],
                             value=heatmap_ticker, clearable=False,
                             style=dict(background=C["card"], width="260px", fontSize="0.82rem")),
            ]),
        ], style=dict(display="flex", gap="20px", flexWrap="wrap",
                      padding="0 24px 14px")),

        # Custom date range section — shown only when "Custom Range" is selected
        html.Div([
            html.Div([
                html.Label("Start Date", style=dict(color=C["muted"], fontSize="0.72rem", display="block", marginBottom="4px")),
                dcc.DatePickerSingle(
                    id="analytics-custom-start",
                    date=None,
                    display_format="DD MMM YYYY",
                    style=dict(fontSize="0.82rem"),
                ),
            ]),
            html.Div([
                html.Label("End Date", style=dict(color=C["muted"], fontSize="0.72rem", display="block", marginBottom="4px")),
                dcc.DatePickerSingle(
                    id="analytics-custom-end",
                    date=None,
                    display_format="DD MMM YYYY",
                    style=dict(fontSize="0.82rem"),
                ),
            ]),
            html.Button("Apply Range", id="analytics-apply-range", n_clicks=0, style=dict(
                background=C["accent"], color=C["header"],
                border="none", borderRadius="8px",
                padding="8px 20px", cursor="pointer", fontSize="0.82rem", fontWeight=700,
                alignSelf="flex-end",
            )),
        ], id="analytics-custom-range-section",
           style=dict(display="none", gap="14px", alignItems="flex-start", flexWrap="wrap")),

        html.Div(style=dict(borderBottom=f"1px solid {C['border']}", margin="0 0 0 0")),

        # Charts grid — all pre-populated with real data
        html.Div([
            # Row 1: indexed growth + ranked bar
            html.Div([
                html.Div([
                    html.Div("💰 Growth of KES 100 invested", style=dict(
                        fontWeight=700, fontSize="0.88rem", color=C["text"],
                        marginBottom="4px")),
                    html.Div("If you had invested KES 100 in each company at the start — who made you more money?",
                             style=dict(fontSize="0.72rem", color=C["muted"], marginBottom="8px")),
                    dcc.Graph(id="chart-indexed",
                              figure=chart_comparison_indexed(tickers, days),
                              config=dict(displayModeBar=False)),
                ], style=dict(flex="2", background=C["card"],
                              border=f"1px solid {C['border']}", borderRadius="10px",
                              padding="16px")),
                html.Div([
                    html.Div("🏆 Best & Worst Performers", style=dict(
                        fontWeight=700, fontSize="0.88rem", color=C["text"],
                        marginBottom="4px")),
                    html.Div("Which company gained or lost the most?",
                             style=dict(fontSize="0.72rem", color=C["muted"], marginBottom="8px")),
                    dcc.Graph(id="chart-ranked",
                              figure=chart_performance_ranked(days),
                              config=dict(displayModeBar=False)),
                ], style=dict(flex="1", background=C["card"],
                              border=f"1px solid {C['border']}", borderRadius="10px",
                              padding="16px")),
            ], style=dict(display="flex", gap="16px")),

            # Row 2: stacked price panels
            html.Div([
                html.Div("📉 Individual Price History (KES)", style=dict(
                    fontWeight=700, fontSize="0.88rem", color=C["text"],
                    marginBottom="4px")),
                html.Div("Actual share price in Kenyan Shillings for each company over the selected period.",
                         style=dict(fontSize="0.72rem", color=C["muted"], marginBottom="8px")),
                dcc.Graph(id="chart-all-prices",
                          figure=chart_all_prices(tickers, days),
                          config=dict(displayModeBar=True, scrollZoom=True)),
            ], style=dict(background=C["card"], border=f"1px solid {C['border']}",
                          borderRadius="10px", padding="16px")),

            # Row 3: monthly heatmap
            html.Div([
                html.Div("📅 Monthly Returns Calendar", style=dict(
                    fontWeight=700, fontSize="0.88rem", color=C["text"],
                    marginBottom="4px")),
                html.Div("Green = the stock went up that month. Red = it went down. "
                         "The darker the colour, the bigger the move.",
                         style=dict(fontSize="0.72rem", color=C["muted"], marginBottom="8px")),
                dcc.Graph(id="chart-heatmap",
                          figure=chart_monthly_heatmap(heatmap_ticker),
                          config=dict(displayModeBar=False)),
            ], style=dict(background=C["card"], border=f"1px solid {C['border']}",
                          borderRadius="10px", padding="16px")),

            # Row 4: performance summary table
            html.Div([
                html.Div("📋 Performance Summary — All Companies", style=dict(
                    fontWeight=700, fontSize="0.88rem", color=C["text"],
                    marginBottom="4px")),
                html.Div("Price changes across different time periods for every company we track.",
                         style=dict(fontSize="0.72rem", color=C["muted"], marginBottom="8px")),
                html.Div(id="summary-table", children=summary_tbl),
            ], style=dict(background=C["card"], border=f"1px solid {C['border']}",
                          borderRadius="10px", padding="16px")),

        ], style=dict(display="flex", flexDirection="column",
                      gap="16px", padding="16px 24px 24px")),
    ], style=dict(overflowY="auto", maxHeight="calc(100vh - 105px)"))


# ── TAB 4: IMPORT & ANALYSE — Add New Company Data ───────────────────────────
def build_import_tab():
    return html.Div([
        html.Div([
            html.Div("📥  Import & Analyse New Company Data", style=dict(
                fontSize="1.15rem", fontWeight=800, color=C["text"])),
            html.Div("Upload a CSV of daily prices, give the company a ticker name, then choose how to analyse it.",
                     style=dict(fontSize="0.83rem", color=C["muted"], marginTop="2px")),
        ], style=dict(padding="20px 24px 16px",
                      borderBottom=f"1px solid {C['border']}")),

        html.Div([
            # Upload zone
            dcc.Upload(id="csv-upload-tab",
                accept=".csv",
                children=html.Div([
                    html.Div("📂", style=dict(fontSize="2.5rem", marginBottom="8px")),
                    html.Div("Click to upload a CSV file", style=dict(
                        fontWeight=700, color=C["accent"], fontSize="1rem")),
                    html.Div("or drag and drop here", style=dict(
                        color=C["muted"], fontSize="0.82rem")),
                    html.Div("Required columns: Date, Open, High, Low, Close, Volume",
                             style=dict(color=C["muted"], fontSize="0.75rem", marginTop="8px")),
                    html.Div(id="upload-filename", style=dict(
                        color=C["buy"], fontSize="0.78rem", marginTop="8px")),
                ], style=dict(textAlign="center", padding="40px")),
                style=dict(border=f"2px dashed {C['border']}", borderRadius="12px",
                           background=C["card"], cursor="pointer", marginBottom="16px",
                           transition="border 0.2s"),
            ),

            # Ticker input
            html.Div([
                html.Label("Company ticker / name:", style=dict(
                    color=C["muted"], fontSize="0.82rem", marginBottom="6px",
                    display="block")),
                dcc.Input(id="import-tab-name", placeholder="e.g. BAMB.NR or UCHUMI.NR",
                          style=dict(background=C["card"], border=f"1px solid {C['border']}",
                                     color=C["text"], borderRadius="8px",
                                     padding="8px 14px", width="260px",
                                     fontSize="0.85rem")),
            ], style=dict(marginBottom="16px")),

            # Buttons row
            html.Div([
                html.Button("⚡ Quick Analysis (30 sec)", id="run-quick-import-btn", style=dict(
                    background=C["accent"], color=C["header"], fontWeight=700,
                    border="none", borderRadius="8px",
                    padding="10px 22px", cursor="pointer", fontSize="0.88rem")),
                html.Button("🧠 Full AI Analysis (10–15 min)", id="run-full-import-btn", style=dict(
                    background="transparent", color=C["accent"], fontWeight=700,
                    border=f"2px solid {C['accent']}", borderRadius="8px",
                    padding="10px 22px", cursor="pointer", fontSize="0.88rem")),
            ], style=dict(display="flex", gap="12px", flexWrap="wrap", marginBottom="16px")),

            # Status display
            html.Div([
                dcc.Loading(html.Div(id="import-tab-status"), type="circle", color=C["accent"]),
                html.Div(id="pipeline-status-display", style=dict(
                    marginTop="8px", padding="12px 16px",
                    background=C["card"], border=f"1px solid {C['border']}",
                    borderRadius="8px", display="none",
                )),
            ], style=dict(marginBottom="16px")),

            # How-to instructions
            html.Div([
                html.Div("📌 How to get NSE data:", style=dict(
                    fontWeight=700, color=C["text"], marginBottom="8px", fontSize="0.88rem")),
                html.Ol([
                    html.Li("Go to the NSE website: nse.co.ke",
                            style=dict(fontSize="0.82rem", color=C["muted"], marginBottom="4px")),
                    html.Li("Navigate to Trade Statistics → Historical Data",
                            style=dict(fontSize="0.82rem", color=C["muted"], marginBottom="4px")),
                    html.Li("Select your company and date range",
                            style=dict(fontSize="0.82rem", color=C["muted"], marginBottom="4px")),
                    html.Li("Download the CSV file",
                            style=dict(fontSize="0.82rem", color=C["muted"], marginBottom="4px")),
                    html.Li("Upload it above, enter the ticker, then click Quick or Full Analysis",
                            style=dict(fontSize="0.82rem", color=C["muted"])),
                ]),
                html.Div([
                    html.Div("Quick Analysis vs Full AI Analysis:", style=dict(
                        fontWeight=700, color=C["text"], marginTop="14px", marginBottom="6px",
                        fontSize="0.85rem")),
                    html.Div([
                        html.Span("⚡ Quick (30 sec)", style=dict(color=C["accent"], fontWeight=700)),
                        html.Span(" — Runs XGBoost only. Gets you a fast signal with no waiting.",
                                  style=dict(color=C["muted"], fontSize="0.8rem")),
                    ], style=dict(marginBottom="4px")),
                    html.Div([
                        html.Span("🧠 Full AI (10–15 min)", style=dict(color=C["accent"], fontWeight=700)),
                        html.Span(" — Runs the complete pipeline: ARIMA + LSTM + XGBoost ensemble. "
                                  "Much more accurate but takes longer. Runs in the background.",
                                  style=dict(color=C["muted"], fontSize="0.8rem")),
                    ]),
                ]),
            ], style=dict(background=C["card"], border=f"1px solid {C['border']}",
                          borderRadius="10px", padding="16px")),

        ], style=dict(padding="16px 24px 24px", maxWidth="720px")),
    ], style=dict(overflowY="auto", maxHeight="calc(100vh - 105px)"))


# ── Callbacks: Company tab ────────────────────────────────────────────────────
@app.callback(
    Output("price-chart-company","figure"),
    Input("price-period","value"),
    State("selected-ticker","data"),
    prevent_initial_call=True,
)
def update_price_chart(days, ticker):
    df = load_df(ticker)
    if df is None: return go.Figure()
    return chart_price_simple(df, ticker, days)


@app.callback(
    Output("analysis-store","data"),
    Output("quick-status","children"),
    Input("quick-btn","n_clicks"),
    State("selected-ticker","data"),
    State("analysis-store","data"),
    prevent_initial_call=True,
)
def run_quick(n, ticker, store):
    if not n: return store, ""
    df = load_df(ticker)
    if df is None:
        return store, html.Span("No data found.", style=dict(color=C["sell"]))
    try:
        result = run_quick_fn(df, ticker)
        store = store or {}
        store[ticker] = {k:v for k,v in result.items()
                         if k not in ("ma_df",) and not isinstance(v, pd.DataFrame)}
        return store, html.Span("✓ Done", style=dict(color=C["buy"], fontSize="0.8rem"))
    except Exception as e:
        return store, html.Span(f"Error: {e}", style=dict(color=C["sell"], fontSize="0.75rem"))


# ── Callbacks: Analytics tab ─────────────────────────────────────────────────
@app.callback(
    Output("chart-indexed","figure"),
    Output("chart-ranked","figure"),
    Output("chart-all-prices","figure"),
    Input("analytics-period","value"),
    Input("analytics-sector","value"),
    Input("analytics-apply-range","n_clicks"),
    State("analytics-custom-start","date"),
    State("analytics-custom-end","date"),
    prevent_initial_call=True,
)
def update_analytics_charts(days, sector, n_apply, custom_start, custom_end):
    tickers  = SECTORS.get(sector, NSE_TICKERS)
    use_days = days if days != 0 else 9999
    use_start = custom_start if days == 0 else None
    use_end   = custom_end   if days == 0 else None
    return (
        chart_comparison_indexed(tickers, use_days, use_start, use_end),
        chart_performance_ranked(use_days, use_start, use_end),
        chart_all_prices(tickers, use_days, use_start, use_end),
    )


@app.callback(
    Output("chart-heatmap","figure"),
    Input("heatmap-ticker","value"),
    prevent_initial_call=True,
)
def update_heatmap(ticker):
    return chart_monthly_heatmap(ticker)


# ── Callbacks: Import tab — upload feedback ───────────────────────────────────
@app.callback(
    Output("upload-filename","children"),
    Input("csv-upload-tab","filename"),
    prevent_initial_call=True,
)
def show_upload_name(filename):
    if not filename:
        return ""
    return f"✓ File ready: {filename}"


# ── Callbacks: Import tab — Quick Analysis button ────────────────────────────
@app.callback(
    Output("selected-ticker","data",        allow_duplicate=True),
    Output("analysis-store","data",         allow_duplicate=True),
    Output("import-tab-status","children"),
    Output("main-tabs","value",             allow_duplicate=True),
    Input("run-quick-import-btn","n_clicks"),
    State("import-tab-name","value"),
    State("csv-upload-tab","contents"),
    State("analysis-store","data"),
    prevent_initial_call=True,
)
def process_quick_import(n, name, contents, store):
    return _process_csv_quick(n, name, contents, store)


def _process_csv_quick(n, name, contents, store):
    no = (dash.no_update, store or {},
          html.Span("Please fill in the company name and upload a CSV.",
                    style=dict(color=C["hold"])),
          dash.no_update)
    if not n or not name or not contents:
        return no
    ticker = name.strip().upper()
    if not ticker.endswith(".NR"):
        ticker += ".NR"
    try:
        _, cs = contents.split(",")
        decoded = base64.b64decode(cs)
        from src.data.fetcher import load_from_csv
        from src.data.cleaner import clean_ohlcv, save_cleaned
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as f:
            f.write(decoded)
            tmp = f.name
        raw = load_from_csv(tmp, ticker=ticker)
        os.unlink(tmp)
        cleaned, _ = clean_ohlcv(raw, ticker=ticker)
        save_cleaned(cleaned, ticker)
        result = run_quick_fn(cleaned, ticker)
        store = store or {}
        store[ticker] = {k:v for k,v in result.items()
                         if k not in ("ma_df",) and not isinstance(v, pd.DataFrame)}
        return (ticker, store,
                html.Span(f"✓ {ticker} analysed! Signal: {result.get('risk_adjusted_signal','—')}",
                          style=dict(color=C["buy"])),
                "company")
    except Exception as e:
        return (dash.no_update, store or {},
                html.Span(f"Error: {e}", style=dict(color=C["sell"], fontSize="0.75rem")),
                dash.no_update)


# ── Callbacks: Import tab — Full AI Analysis (background subprocess) ──────────
@app.callback(
    Output("pipeline-ticker","data"),
    Output("pipeline-csv-path","data"),
    Output("pipeline-status-display","children"),
    Output("pipeline-status-display","style"),
    Output("pipeline-poll","disabled"),
    Input("run-full-import-btn","n_clicks"),
    State("import-tab-name","value"),
    State("csv-upload-tab","contents"),
    State("csv-upload-tab","filename"),
    prevent_initial_call=True,
)
def start_full_pipeline(n, name, contents, filename):
    _hidden = dict(display="none")
    _visible = dict(
        marginTop="8px", padding="12px 16px",
        background=C["card"], border=f"1px solid {C['border']}",
        borderRadius="8px", display="block",
    )
    no = ("", "", dash.no_update, _hidden, True)
    if not n or not name or not contents:
        return ("", "",
                html.Span("Please enter a ticker and upload a CSV first.",
                          style=dict(color=C["hold"])),
                _visible, True)

    ticker = name.strip().upper()
    if not ticker.endswith(".NR"):
        ticker += ".NR"

    try:
        # Save CSV to DATA_RAW
        _, cs = contents.split(",")
        decoded = base64.b64decode(cs)
        DATA_RAW.mkdir(parents=True, exist_ok=True)
        safe_name = filename or f"{ticker.replace('.','_')}.csv"
        csv_path = DATA_RAW / safe_name
        with open(csv_path, "wb") as f:
            f.write(decoded)

        # Write initial status JSON
        DATA_FEATURES.mkdir(parents=True, exist_ok=True)
        status_path = DATA_FEATURES / f"{ticker.replace('.','_')}_pipeline_status.json"
        with open(status_path, "w") as f:
            json.dump({"status": "running", "step": "Saving data..."}, f)

        # Launch subprocess
        subprocess.Popen(
            [sys.executable, str(Path(__file__).parent / "main.py"),
             "--ticker", ticker, "--csv", str(csv_path)],
            cwd=str(Path(__file__).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        msg = html.Div([
            html.Div("🧠 Full AI pipeline started!", style=dict(
                color=C["accent"], fontWeight=700, marginBottom="4px")),
            html.Div(f"Analysing {ticker} — this runs ARIMA + LSTM + XGBoost in the background.",
                     style=dict(color=C["muted"], fontSize="0.82rem", marginBottom="4px")),
            html.Div("Status will update every 3 seconds below. You can use other tabs while waiting.",
                     style=dict(color=C["muted"], fontSize="0.78rem")),
        ])
        return (ticker, str(csv_path), msg, _visible, False)

    except Exception as e:
        return ("", "",
                html.Span(f"Error starting pipeline: {e}",
                          style=dict(color=C["sell"], fontSize="0.75rem")),
                _visible, True)


@app.callback(
    Output("pipeline-status-display","children",  allow_duplicate=True),
    Output("pipeline-status-display","style",     allow_duplicate=True),
    Output("pipeline-poll","disabled",             allow_duplicate=True),
    Output("selected-ticker","data",               allow_duplicate=True),
    Output("main-tabs","value",                    allow_duplicate=True),
    Input("pipeline-poll","n_intervals"),
    State("pipeline-ticker","data"),
    State("selected-ticker","data"),
    prevent_initial_call=True,
)
def poll_pipeline_status(n_intervals, pipeline_ticker, current_ticker):
    _hidden = dict(display="none")
    _visible = dict(
        marginTop="8px", padding="12px 16px",
        background=C["card"], border=f"1px solid {C['border']}",
        borderRadius="8px", display="block",
    )
    no_nav = (dash.no_update, dash.no_update, dash.no_update,
              current_ticker, dash.no_update)

    if not pipeline_ticker:
        return (dash.no_update, _hidden, True, current_ticker, dash.no_update)

    status_path = DATA_FEATURES / f"{pipeline_ticker.replace('.','_')}_pipeline_status.json"
    signal_path = DATA_FEATURES / f"{pipeline_ticker.replace('.','_')}_signal.json"

    # Check if full signal file appeared (pipeline completed)
    if signal_path.exists():
        sig = load_sig(pipeline_ticker)
        final_signal = sig.get("risk_adjusted_signal", "—") if sig else "—"
        adv = ADVICE.get(final_signal, {})
        done_msg = html.Div([
            html.Div(f"✅ Done! Analysis complete for {pipeline_ticker}",
                     style=dict(color=C["buy"], fontWeight=700, marginBottom="6px")),
            html.Div([
                html.Span("Signal: ", style=dict(color=C["muted"])),
                html.Span(f"{adv.get('emoji','')} {final_signal}",
                          style=dict(color=adv.get("color", C["text"]),
                                     fontWeight=700, fontSize="1.1rem")),
            ]),
            html.Div("Switching to Company tab…",
                     style=dict(color=C["muted"], fontSize="0.78rem", marginTop="4px")),
        ])
        # Stop polling, navigate to company tab
        return (done_msg, _visible, True, pipeline_ticker, "company")

    # Read status JSON if available
    step = "Training models…"
    if status_path.exists():
        try:
            with open(status_path) as f:
                st = json.load(f)
            step = st.get("step", "Training models…")
        except Exception:
            pass

    steps = ["Saving data…", "Training models…", "Running ARIMA…",
             "Running LSTM…", "Running XGBoost…", "Generating signal…"]
    progress_msg = html.Div([
        html.Div(f"🔄 Running full pipeline for {pipeline_ticker}…",
                 style=dict(color=C["accent"], fontWeight=700, marginBottom="4px")),
        html.Div(f"Current step: {step}",
                 style=dict(color=C["muted"], fontSize="0.82rem")),
        html.Div("This may take 10–15 minutes. Status updates every 3 seconds.",
                 style=dict(color=C["muted"], fontSize="0.75rem", marginTop="4px")),
    ])
    return (progress_msg, _visible, False, current_ticker, dash.no_update)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — NSE DATA EXPLORER
# ══════════════════════════════════════════════════════════════════════════════

_ARCHIVE_DIR = Path(r"C:\Users\moeng\Downloads\archive")

_NSE_COLS_ORDERED = [
    "Date", "Code", "Name",
    "12m Low", "12m High",
    "Day Low", "Day High", "Day Price",
    "Previous", "Change", "Change%",
    "Volume", "Adjusted Price",
]

_FIELD_GLOSSARY = {
    "Date":           "Trading date",
    "Code":           "NSE ticker symbol (e.g. EQTY, KCB, SCOM)",
    "Name":           "Full company name as listed on the NSE",
    "12m Low":        "Lowest price traded in the past 12 months",
    "12m High":       "Highest price traded in the past 12 months",
    "Day Low":        "Lowest price traded during this session",
    "Day High":       "Highest price traded during this session",
    "Day Price":      "Official closing price for the session (KES)",
    "Previous":       "Previous session's official closing price (KES)",
    "Change":         "Price change in KES  (Day Price − Previous)",
    "Change%":        "Percentage price change vs previous session",
    "Volume":         "Number of shares traded during the session",
    "Adjusted Price": "Price adjusted for corporate actions (splits, dividends)",
}

_ALL_NSE_CODES = [
    "ABSA","ALP","AMAC","BAT","BKG","BOC","BRIT","CARB","CGEN","CIC",
    "COOP","CRWN","CTUM","DTK","EABL","EGAD","EQTY","EVRD","FMLY","FTGH",
    "GLD","HAFR","HFCK","IMH","JUB","KAPC","KCB","KEGN","KNRE","KPC",
    "KPLC","KQ","KUKZ","KURV","LBTY","LIMT","LKL","NBV","NCBA","NMG",
    "NSE","OCH","PORT","SASN","SBIC","SCAN","SCBK","SCOM","SGL","SKL",
    "SLAM","SMER","SMWF","TOTL","TPSE","TRFC","UCHM","UMME","UNGA","WTK","XPRS",
]

# Company name lookup (code → full name) built once from the latest archive year
def _build_name_map():
    path = _ARCHIVE_DIR / "NSE_data_all_stocks_2026.csv"
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path, dtype=str, usecols=["Code", "Name"])
        df["Code"] = df["Code"].str.strip()
        df["Name"] = df["Name"].str.strip()
        return dict(zip(df["Code"], df["Name"]))
    except Exception:
        return {}

_NAME_MAP = _build_name_map()

# Earliest / latest dates available in the archive (used for picker bounds)
def _archive_date_bounds():
    years = sorted(
        int(p.stem.split("_")[-1])
        for p in _ARCHIVE_DIR.glob("NSE_data_all_stocks_????.csv")
        if p.stem.split("_")[-1].isdigit()
    )
    min_year = years[0] if years else 2000
    max_year = years[-1] if years else 2026
    return f"{min_year}-01-01", f"{max_year}-12-31"

_ARCHIVE_MIN_DATE, _ARCHIVE_MAX_DATE = _archive_date_bounds()


# ── Archive data loader ───────────────────────────────────────────────────────

def _load_archive_range(codes, start_date, end_date):
    start = pd.to_datetime(start_date)
    end   = pd.to_datetime(end_date)
    years = range(start.year, end.year + 1)
    frames = []
    for year in years:
        path = _ARCHIVE_DIR / f"NSE_data_all_stocks_{year}.csv"
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path, dtype=str)
            df.columns = [c.strip() for c in df.columns]
            if "Code" not in df.columns or "Date" not in df.columns:
                continue
            df["Code"] = df["Code"].str.strip()
            if codes:
                df = df[df["Code"].isin(codes)]
            if df.empty:
                continue
            # dayfirst=False: handles M/D/YYYY (2026 files) and named-month formats correctly
            df["_dt"] = pd.to_datetime(
                df["Date"].str.strip(), dayfirst=False, format="mixed", errors="coerce"
            )
            df = df.dropna(subset=["_dt"])
            frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined = combined[(combined["_dt"] >= start) & (combined["_dt"] <= end)]
    return combined.sort_values(["_dt", "Code"]).reset_index(drop=True)


def _to_num(series):
    return pd.to_numeric(
        series.astype(str)
              .str.replace(",", "", regex=False)
              .str.replace("%", "", regex=False)
              .str.strip()
              .replace(["-", "", "nan", "NaN", "N/A", "0"], None),
        errors="coerce",
    )


# ── Stats & Top-Movers helpers ────────────────────────────────────────────────

def _compute_stats(df):
    """Return summary stats dict and top-movers list from loaded archive df."""
    if df.empty:
        return {}, []

    prices = _to_num(df["Day Price"]) if "Day Price" in df.columns else pd.Series(dtype=float)
    changes = _to_num(df["Change%"]) if "Change%" in df.columns else pd.Series(dtype=float)
    volumes = _to_num(df["Volume"])  if "Volume"  in df.columns else pd.Series(dtype=float)

    # Per-company total return: last Day Price / first Day Price - 1
    # Exclude stocks where price scale looks inconsistent (ratio > 100x suggests data error)
    returns = {}
    for code, grp in df.groupby("Code"):
        p = _to_num(grp.sort_values("_dt")["Day Price"]).dropna()
        if len(p) >= 2 and p.min() > 0:
            ratio = p.max() / p.min()
            if ratio < 10:   # only include if max/min < 10x (sane price range)
                returns[code] = (p.iloc[-1] / p.iloc[0] - 1) * 100

    best_code  = max(returns, key=returns.get) if returns else "—"
    worst_code = min(returns, key=returns.get) if returns else "—"
    best_pct   = returns.get(best_code, 0)
    worst_pct  = returns.get(worst_code, 0)

    biggest_day = changes.abs().max()
    biggest_row = df.loc[changes.abs().idxmax()] if not changes.dropna().empty else None

    stats = {
        "best_code":  best_code,
        "best_pct":   best_pct,
        "worst_code": worst_code,
        "worst_pct":  worst_pct,
        "biggest_day_pct": biggest_day if pd.notna(biggest_day) else 0,
        "biggest_day_info": (
            f"{biggest_row['Code']} on {pd.to_datetime(biggest_row['_dt']).strftime('%d %b %Y')}"
            if biggest_row is not None else "—"
        ),
        "avg_volume":  volumes.mean(),
        "total_records": len(df),
    }

    # Top movers: sort by total return
    sorted_returns = sorted(returns.items(), key=lambda x: x[1], reverse=True)
    top_gainers = sorted_returns[:3]
    top_losers  = sorted_returns[-3:][::-1]
    movers = [("gain", c, p) for c, p in top_gainers] + [("loss", c, p) for c, p in top_losers]
    return stats, movers


# ── Chart builder ─────────────────────────────────────────────────────────────

def _build_chart(df, chart_type="line"):
    if df.empty:
        return go.Figure()

    palette = ["#38bdf8","#a78bfa","#f472b6","#fb923c","#34d399",
               "#f59e0b","#60a5fa","#e879f9","#4ade80","#fbbf24",
               "#c084fc","#818cf8","#f87171","#2dd4bf","#facc15"]

    codes = sorted(df["Code"].unique())
    multi = len(codes) > 1

    if chart_type == "candlestick" and not multi:
        # Single-stock candlestick + volume subplot
        code = codes[0]
        sub  = df[df["Code"] == code].sort_values("_dt")
        close  = _to_num(sub["Day Price"])
        open_  = _to_num(sub["Previous"])
        high   = _to_num(sub["Day High"])   if "Day High" in sub.columns else close
        low    = _to_num(sub["Day Low"])    if "Day Low"  in sub.columns else close
        volume = _to_num(sub["Volume"])     if "Volume"   in sub.columns else pd.Series(dtype=float)
        name   = _NAME_MAP.get(code, code)

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.72, 0.28], vertical_spacing=0.03,
        )
        vol_colors = [C["buy"] if (c >= o) else C["sell"]
                      for c, o in zip(close.fillna(0), open_.fillna(0))]
        fig.add_trace(go.Candlestick(
            x=sub["_dt"], open=open_, high=high, low=low, close=close,
            name=f"{code} — {name}",
            increasing_line_color=C["buy"], decreasing_line_color=C["sell"],
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            x=sub["_dt"], y=volume, name="Volume",
            marker_color=vol_colors, opacity=0.7, showlegend=False,
        ), row=2, col=1)
        fig.update_layout(
            **CHART_BASE, height=480,
            title=dict(text=f"{code}  —  {name}  |  Candlestick + Volume", font=dict(color=C["accent"])),
            xaxis_rangeslider_visible=False,
        )
        fig.update_yaxes(title_text="Price (KES)", gridcolor=C["border"], row=1, col=1)
        fig.update_yaxes(title_text="Volume",      gridcolor=C["border"], row=2, col=1)
        fig.update_xaxes(gridcolor=C["border"], zeroline=False)
        return fig

    # Line chart (multi-stock or single-stock)
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.72, 0.28], vertical_spacing=0.03,
    )
    for i, code in enumerate(codes):
        sub    = df[df["Code"] == code].sort_values("_dt")
        price  = _to_num(sub["Day Price"])
        volume = _to_num(sub["Volume"]) if "Volume" in sub.columns else pd.Series(dtype=float)
        name   = _NAME_MAP.get(code, code)
        color  = palette[i % len(palette)]

        fig.add_trace(go.Scatter(
            x=sub["_dt"], y=price,
            name=f"{code} — {name}" if not multi else code,
            line=dict(color=color, width=1.8),
            hovertemplate=f"<b>{code}</b><br>%{{x|%d %b %Y}}<br>KES %{{y:,.2f}}<extra></extra>",
        ), row=1, col=1)

        if not multi:
            vol_colors = [C["buy"] if (c >= p) else C["sell"]
                          for c, p in zip(
                              _to_num(sub["Day Price"]).fillna(0),
                              _to_num(sub["Previous"]).fillna(0),
                          )]
            fig.add_trace(go.Bar(
                x=sub["_dt"], y=volume, name="Volume",
                marker_color=vol_colors, opacity=0.7, showlegend=False,
            ), row=2, col=1)

    title_text = (
        "Daily Price — Day Price (KES)" if multi
        else f"{codes[0]}  —  {_NAME_MAP.get(codes[0], codes[0])}  |  Price + Volume"
    )
    fig.update_layout(
        **{**CHART_BASE, "legend": dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10))},
        height=480,
        title=dict(text=title_text, font=dict(color=C["accent"])),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Price (KES)", gridcolor=C["border"], row=1, col=1)
    fig.update_yaxes(title_text="Volume",      gridcolor=C["border"], row=2, col=1)
    fig.update_xaxes(gridcolor=C["border"], zeroline=False)
    return fig


# ── UI helpers ────────────────────────────────────────────────────────────────

def _stat_card(label, value, value_color=None, sub=None):
    return html.Div([
        html.Div(label, style=dict(
            fontSize="0.62rem", color=C["muted"],
            textTransform="uppercase", letterSpacing="0.08em", marginBottom="4px",
        )),
        html.Div(value, style=dict(
            fontSize="1.1rem", fontWeight=800,
            color=value_color or C["text"],
        )),
        html.Div(sub or "", style=dict(fontSize="0.68rem", color=C["muted"], marginTop="2px")),
    ], style=dict(
        background=C["card"], border=f"1px solid {C['border']}",
        borderRadius="10px", padding="14px 18px", flex="1", minWidth="160px",
    ))


def _mover_badge(code, pct, is_gain):
    color = C["buy"] if is_gain else C["sell"]
    bg    = "#052e1640" if is_gain else "#2d0a0a40"
    arrow = "▲" if is_gain else "▼"
    name  = _NAME_MAP.get(code, code)
    return html.Div([
        html.Span(f"{arrow} {code}", style=dict(fontWeight=800, color=color, fontSize="0.82rem")),
        html.Div(name,               style=dict(fontSize="0.65rem", color=C["muted"])),
        html.Div(f"{pct:+.1f}%",    style=dict(fontWeight=700, color=color, fontSize="0.85rem")),
    ], style=dict(
        background=bg, border=f"1px solid {color}50",
        borderRadius="8px", padding="8px 14px", textAlign="center", minWidth="90px",
    ))


# ── Tab builder ───────────────────────────────────────────────────────────────

def build_explorer_tab():
    from datetime import date, timedelta
    today         = date.today()
    default_start = (today - timedelta(days=30)).isoformat()
    default_end   = today.isoformat()

    code_options = [
        {"label": f"{c}  —  {_NAME_MAP.get(c, '')}", "value": c}
        for c in _ALL_NSE_CODES
    ]

    # Field glossary rows
    glossary_rows = [
        html.Tr([
            html.Td(col, style=dict(fontWeight=700, color=C["accent"], fontSize="0.78rem",
                                    padding="4px 12px 4px 0", whiteSpace="nowrap")),
            html.Td(desc, style=dict(color=C["muted"], fontSize="0.78rem", padding="4px 0")),
        ])
        for col, desc in _FIELD_GLOSSARY.items()
    ]

    guidance = html.Div([
        # Quick-start
        html.Div([
            html.Div("Quick Start", style=dict(fontWeight=700, color=C["text"],
                                               fontSize="0.85rem", marginBottom="8px")),
            html.Ol([
                html.Li("Pick a date range below  (data available: 2000 → today — upload earlier years via template)",
                        style=dict(color=C["muted"], fontSize="0.8rem", marginBottom="4px")),
                html.Li("Select the companies you want  (all 62 are pre-selected)",
                        style=dict(color=C["muted"], fontSize="0.8rem", marginBottom="4px")),
                html.Li("Click  Load Data  — chart, stats and table appear instantly",
                        style=dict(color=C["muted"], fontSize="0.8rem", marginBottom="4px")),
                html.Li("Toggle Candlestick / Line with the chart button",
                        style=dict(color=C["muted"], fontSize="0.8rem", marginBottom="4px")),
                html.Li("Download as CSV or Excel when you're done",
                        style=dict(color=C["muted"], fontSize="0.8rem")),
            ], style=dict(paddingLeft="18px", margin=0)),
        ], style=dict(flex="1", minWidth="280px")),

        # Field glossary
        html.Div([
            html.Div("Column Guide — what every NSE field means",
                     style=dict(fontWeight=700, color=C["text"],
                                fontSize="0.85rem", marginBottom="8px")),
            html.Table(html.Tbody(glossary_rows), style=dict(borderCollapse="collapse")),
        ], style=dict(flex="2", minWidth="340px")),

    ], style=dict(
        display="flex", gap="32px", flexWrap="wrap",
        background=C["panel"], border=f"1px solid {C['border']}",
        borderRadius="10px", padding="18px 24px", margin="16px 24px 0",
    ))

    toggle_btn_style = dict(
        border=f"1px solid {C['border']}", borderRadius="20px",
        padding="6px 14px", cursor="pointer", fontSize="0.8rem",
        fontWeight=600, background=C["card"], color=C["muted"],
    )

    return html.Div([
        # ── Header ──────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.Span("📅  NSE Data Explorer",
                          style=dict(fontSize="1.15rem", fontWeight=800, color=C["text"])),
                html.Span(
                    f"  ·  Data available: 2007 – {pd.Timestamp('today').strftime('%d %b %Y')}  "
                    f"·  {len(_ALL_NSE_CODES)} companies",
                    style=dict(fontSize="0.75rem", color=C["muted"], marginLeft="8px"),
                ),
            ]),
            html.Button(
                "▼ Field Guide", id="explorer-guide-toggle", n_clicks=0,
                style={**toggle_btn_style, "background": "transparent"},
            ),
        ], style=dict(
            display="flex", justifyContent="space-between", alignItems="center",
            padding="16px 24px 8px",
            borderBottom=f"1px solid {C['border']}",
        )),

        # ── Collapsible guidance panel ───────────────────────────────────────
        html.Div(guidance, id="explorer-guide-panel", style=dict(display="none")),

        # ── Sticky controls bar ──────────────────────────────────────────────
        html.Div([
            # Date range
            html.Div([
                html.Label("Date Range",
                           style=dict(color=C["muted"], fontSize="0.72rem",
                                      display="block", marginBottom="5px",
                                      textTransform="uppercase", letterSpacing="0.07em")),
                html.Div([
                    html.Span("Quick pick:", style=dict(fontSize="0.7rem", color=C["muted"],
                                                         alignSelf="center", marginRight="4px")),
                    *[html.Button(lbl, id=f"explorer-preset-{key}", n_clicks=0, style=dict(
                        background=C["card"], color=C["accent"],
                        border=f"1px solid {C['border']}", borderRadius="14px",
                        padding="3px 10px", cursor="pointer", fontSize="0.72rem", fontWeight=600,
                        marginRight="4px",
                    )) for lbl, key in [("7D","7d"),("30D","30d"),("3M","3m"),("1Y","1y"),("YTD","ytd"),("Max","max")]
                    ],
                ], style=dict(display="flex", alignItems="center", flexWrap="wrap", marginBottom="6px")),
                dcc.DatePickerRange(
                    id="explorer-dates",
                    start_date=default_start,
                    end_date=default_end,
                    min_date_allowed=_ARCHIVE_MIN_DATE,
                    max_date_allowed=_ARCHIVE_MAX_DATE,
                    display_format="DD MMM YYYY",
                    minimum_nights=0,
                    style=dict(fontSize="0.82rem"),
                ),
            ], style=dict(flex="0 0 auto")),

            # Company selector
            html.Div([
                html.Div([
                    html.Label("Companies",
                               style=dict(color=C["muted"], fontSize="0.72rem",
                                          display="block", marginBottom="5px",
                                          textTransform="uppercase", letterSpacing="0.07em")),
                    html.Div([
                        html.Span("All 62 pre-selected",
                                  style=dict(fontSize="0.72rem", color=C["buy"])),
                        html.Button("Select All", id="explorer-select-all", n_clicks=0,
                                    style=dict(marginLeft="10px", background="transparent",
                                               color=C["accent"], border=f"1px solid {C['accent']}",
                                               borderRadius="12px", padding="2px 10px",
                                               cursor="pointer", fontSize="0.72rem")),
                        html.Button("Clear", id="explorer-clear", n_clicks=0,
                                    style=dict(marginLeft="6px", background="transparent",
                                               color=C["muted"], border=f"1px solid {C['border']}",
                                               borderRadius="12px", padding="2px 10px",
                                               cursor="pointer", fontSize="0.72rem")),
                    ], style=dict(display="flex", alignItems="center", marginBottom="5px")),
                ]),
                dcc.Dropdown(
                    id="explorer-codes",
                    options=code_options,
                    value=_ALL_NSE_CODES,
                    multi=True,
                    placeholder="Search and select companies…",
                    style=dict(background=C["card"], fontSize="0.82rem", minWidth="380px"),
                ),
            ], style=dict(flex="1", minWidth="300px")),

            # Action buttons
            html.Div([
                html.Div("Set date range & companies above, then:",
                         style=dict(fontSize="0.68rem", color=C["muted"], marginBottom="5px")),
                html.Button("Load Data", id="explorer-load", n_clicks=0, style=dict(
                    background=C["accent"], color=C["header"],
                    fontWeight=800, border="none", borderRadius="8px",
                    padding="12px 32px", cursor="pointer", fontSize="0.95rem",
                    letterSpacing="0.03em", width="100%",
                )),
            ], style=dict(display="flex", flexDirection="column", alignItems="flex-end", paddingBottom="2px")),

        ], style=dict(
            display="flex", gap="20px", flexWrap="wrap", alignItems="flex-start",
            padding="14px 24px 14px",
            background=C["panel"],
            borderBottom=f"1px solid {C['border']}",
            position="sticky", top="0", zIndex="100",
        )),

        # ── Results area (stats, movers, table) ─────────────────────────────
        dcc.Loading(
            html.Div(
                html.Div(
                    "Select a date range and companies, then click Load Data.",
                    style=dict(color=C["muted"], padding="48px 24px",
                               fontSize="0.9rem", textAlign="center"),
                ),
                id="explorer-results",
            ),
            type="dot", color=C["accent"],
        ),

        # ── Chart section — static, always in DOM ────────────────────────────
        html.Div([
            html.Div([
                html.Div("Price Chart",
                         style=dict(fontWeight=700, color=C["text"], fontSize="0.9rem")),
                html.Div([
                    html.Div("Chart type:", style=dict(
                        color=C["muted"], fontSize="0.78rem",
                        marginRight="8px", alignSelf="center",
                    )),
                    html.Button("Line", id="explorer-toggle-line", n_clicks=0, style=dict(
                        background=C["accent"], color=C["header"],
                        border=f"1px solid {C['border']}", borderRadius="6px 0 0 6px",
                        padding="5px 14px", cursor="pointer", fontSize="0.8rem", fontWeight=600,
                    )),
                    html.Button("Candlestick", id="explorer-toggle-candle", n_clicks=0, style=dict(
                        background=C["card"], color=C["muted"],
                        border=f"1px solid {C['border']}", borderLeft="none",
                        borderRadius="0 6px 6px 0",
                        padding="5px 14px", cursor="pointer", fontSize="0.8rem", fontWeight=600,
                    )),
                ], style=dict(display="flex", alignItems="center")),
            ], style=dict(display="flex", justifyContent="space-between",
                          alignItems="center", marginBottom="10px")),
            dcc.Graph(
                id="explorer-chart",
                figure=go.Figure(layout=dict(
                    paper_bgcolor=C["card"], plot_bgcolor=C["card"], height=480,
                    xaxis=dict(visible=False), yaxis=dict(visible=False),
                    annotations=[dict(text="Load data to see the chart", showarrow=False,
                                     font=dict(color=C["muted"], size=14))],
                )),
                config=dict(displayModeBar=True, scrollZoom=True,
                            modeBarButtonsToRemove=["lasso2d", "select2d"]),
            ),
        ], id="explorer-chart-section",
           style=dict(display="none", padding="16px 24px",
                      borderBottom=f"1px solid {C['border']}")),

        # ── Export bar — static, always in DOM ───────────────────────────────
        html.Div([
            html.Button("Download CSV", id="explorer-dl-csv", n_clicks=0, style=dict(
                background="transparent", color=C["buy"],
                border=f"1px solid {C['buy']}", borderRadius="8px",
                padding="8px 20px", cursor="pointer", fontSize="0.83rem", fontWeight=600,
            )),
            html.Button("Download Excel (.xlsx)", id="explorer-dl-excel", n_clicks=0, style=dict(
                background="transparent", color=C["accent"],
                border=f"1px solid {C['accent']}", borderRadius="8px",
                padding="8px 20px", cursor="pointer", fontSize="0.83rem", fontWeight=600,
            )),
        ], id="explorer-export-bar",
           style=dict(display="none", gap="12px", padding="16px 24px 32px")),

    ], style=dict(overflowY="auto", maxHeight="calc(100vh - 105px)"))


# ── Results renderer ─────────────────────────────────────────────────────────

def _render_results(df):
    if df.empty:
        return html.Div(
            "No data found for this selection. Try a wider date range or different companies.",
            style=dict(color=C["muted"], padding="48px 24px", textAlign="center"),
        )

    stats, movers = _compute_stats(df)
    n_codes = df["Code"].nunique()
    min_dt  = df["_dt"].min().strftime("%d %b %Y")
    max_dt  = df["_dt"].max().strftime("%d %b %Y")

    # ── Summary stats strip ──────────────────────────────────────────────────
    stats_strip = html.Div([
        _stat_card("Best Performer",
                   f"{stats['best_code']}  {stats['best_pct']:+.1f}%",
                   C["buy"],
                   _NAME_MAP.get(stats["best_code"], "")),
        _stat_card("Worst Performer",
                   f"{stats['worst_code']}  {stats['worst_pct']:+.1f}%",
                   C["sell"],
                   _NAME_MAP.get(stats["worst_code"], "")),
        _stat_card("Biggest Single-Day Move",
                   f"{stats['biggest_day_pct']:+.1f}%",
                   C["hold"],
                   stats["biggest_day_info"]),
        _stat_card("Total Records",
                   f"{stats['total_records']:,}",
                   C["accent"],
                   f"{n_codes} companies  ·  {min_dt} → {max_dt}"),
    ], style=dict(
        display="flex", gap="12px", flexWrap="wrap",
        padding="16px 24px", borderBottom=f"1px solid {C['border']}",
    ))

    # ── Top Movers strip ────────────────────────────────────────────────────
    mover_badges = []
    gainers = [(c, p) for t, c, p in movers if t == "gain"]
    losers  = [(c, p) for t, c, p in movers if t == "loss"]
    if gainers or losers:
        mover_badges = [
            html.Div("Top Gainers", style=dict(
                fontSize="0.68rem", color=C["buy"], fontWeight=700,
                textTransform="uppercase", letterSpacing="0.08em",
                marginRight="4px", alignSelf="center",
            )),
            *[_mover_badge(c, p, True)  for c, p in gainers],
            html.Div("", style=dict(width="1px", background=C["border"],
                                    margin="0 12px", alignSelf="stretch")),
            html.Div("Top Losers", style=dict(
                fontSize="0.68rem", color=C["sell"], fontWeight=700,
                textTransform="uppercase", letterSpacing="0.08em",
                marginRight="4px", alignSelf="center",
            )),
            *[_mover_badge(c, p, False) for c, p in losers],
        ]

    movers_strip = html.Div(mover_badges, style=dict(
        display="flex", gap="8px", flexWrap="wrap", alignItems="center",
        padding="12px 24px", borderBottom=f"1px solid {C['border']}",
        background=C["panel"],
    )) if mover_badges else html.Div()

    # ── Data table — all 13 NSE columns ─────────────────────────────────────
    df_disp = df.copy()
    df_disp["Date"] = df_disp["_dt"].dt.strftime("%d/%m/%Y")
    cols_present = [c for c in _NSE_COLS_ORDERED if c in df_disp.columns]
    df_disp = df_disp[cols_present]

    table_section = html.Div([
        html.Div([
            html.Div("Full NSE Data  —  all 13 columns",
                     style=dict(fontWeight=700, color=C["text"], fontSize="0.88rem")),
            html.Div("Sort any column · Filter using the search row · 100 rows per page",
                     style=dict(fontSize="0.72rem", color=C["muted"], marginTop="2px")),
        ], style=dict(marginBottom="12px")),

        dash_table.DataTable(
            id="explorer-table",
            data=df_disp.to_dict("records"),
            columns=[{"name": c, "id": c} for c in cols_present],
            page_size=100,
            sort_action="native",
            filter_action="native",
            style_table=dict(overflowX="auto", minWidth="100%"),
            style_header=dict(
                background=C["panel"], color=C["muted"],
                fontWeight=700, fontSize="0.7rem",
                border=f"1px solid {C['border']}",
                textTransform="uppercase", letterSpacing="0.05em",
                whiteSpace="nowrap",
            ),
            style_cell=dict(
                background=C["card"], color=C["text"],
                fontSize="0.82rem", padding="7px 12px",
                border=f"1px solid {C['border']}",
                fontVariantNumeric="tabular-nums",
                whiteSpace="nowrap",
            ),
            style_data_conditional=[
                {"if": {"column_id": "Day Price"}, "fontWeight": 700, "color": C["accent"]},
                {"if": {"column_id": "Code"},      "fontWeight": 700},
                {"if": {"column_id": "Change",  "filter_query": "{Change} > 0"},
                 "color": C["buy"],  "fontWeight": 600},
                {"if": {"column_id": "Change",  "filter_query": "{Change} < 0"},
                 "color": C["sell"], "fontWeight": 600},
                {"if": {"column_id": "Change%", "filter_query": "{Change%} > 0"},
                 "color": C["buy"],  "fontWeight": 600},
                {"if": {"column_id": "Change%", "filter_query": "{Change%} < 0"},
                 "color": C["sell"], "fontWeight": 600},
            ],
        ),

    ], style=dict(padding="16px 24px 32px"))

    return html.Div([stats_strip, movers_strip, table_section])


# ── Explorer Callbacks ────────────────────────────────────────────────────────

@app.callback(
    Output("explorer-guide-panel", "style"),
    Input("explorer-guide-toggle", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_guide(n):
    return dict(display="block") if n % 2 == 1 else dict(display="none")


@app.callback(
    Output("explorer-dates", "start_date"),
    Output("explorer-dates", "end_date"),
    Input("explorer-preset-7d",  "n_clicks"),
    Input("explorer-preset-30d", "n_clicks"),
    Input("explorer-preset-3m",  "n_clicks"),
    Input("explorer-preset-1y",  "n_clicks"),
    Input("explorer-preset-ytd", "n_clicks"),
    Input("explorer-preset-max", "n_clicks"),
    prevent_initial_call=True,
)
def explorer_date_preset(_7d, _30d, _3m, _1y, _ytd, _max):
    from datetime import date, timedelta
    today = date.today()
    presets = {
        "explorer-preset-7d":  (today - timedelta(days=7),   today),
        "explorer-preset-30d": (today - timedelta(days=30),  today),
        "explorer-preset-3m":  (today - timedelta(days=91),  today),
        "explorer-preset-1y":  (today - timedelta(days=365), today),
        "explorer-preset-ytd": (date(today.year, 1, 1),      today),
        "explorer-preset-max": (date(2000, 1, 1),            today),
    }
    start, end = presets.get(ctx.triggered_id, (today - timedelta(days=30), today))
    return start.isoformat(), end.isoformat()


@app.callback(
    Output("explorer-codes", "value"),
    Input("explorer-select-all", "n_clicks"),
    Input("explorer-clear",      "n_clicks"),
    prevent_initial_call=True,
)
def explorer_code_buttons(n_all, n_clear):
    return _ALL_NSE_CODES if ctx.triggered_id == "explorer-select-all" else []


_CHART_VISIBLE  = dict(display="block", padding="16px 24px", borderBottom=f"1px solid {C['border']}")
_CHART_HIDDEN   = dict(display="none",  padding="16px 24px", borderBottom=f"1px solid {C['border']}")
_EXPORT_VISIBLE = dict(display="flex",  gap="12px", padding="16px 24px 32px")
_EXPORT_HIDDEN  = dict(display="none",  gap="12px", padding="16px 24px 32px")

_LINE_ACTIVE = dict(
    background=C["accent"], color=C["header"],
    border=f"1px solid {C['border']}", borderRadius="6px 0 0 6px",
    padding="5px 14px", cursor="pointer", fontSize="0.8rem", fontWeight=600,
)
_LINE_INACTIVE = dict(
    background=C["card"], color=C["muted"],
    border=f"1px solid {C['border']}", borderRadius="6px 0 0 6px",
    padding="5px 14px", cursor="pointer", fontSize="0.8rem", fontWeight=600,
)
_CANDLE_ACTIVE = dict(
    background=C["accent"], color=C["header"],
    border=f"1px solid {C['border']}", borderLeft="none", borderRadius="0 6px 6px 0",
    padding="5px 14px", cursor="pointer", fontSize="0.8rem", fontWeight=600,
)
_CANDLE_INACTIVE = dict(
    background=C["card"], color=C["muted"],
    border=f"1px solid {C['border']}", borderLeft="none", borderRadius="0 6px 6px 0",
    padding="5px 14px", cursor="pointer", fontSize="0.8rem", fontWeight=600,
)


@app.callback(
    Output("explorer-results",       "children"),
    Output("explorer-data",          "data"),
    Output("explorer-chart-section", "style"),
    Output("explorer-export-bar",    "style"),
    Input("explorer-load", "n_clicks"),
    State("explorer-dates", "start_date"),
    State("explorer-dates", "end_date"),
    State("explorer-codes", "value"),
    prevent_initial_call=True,
)
def explorer_load(n_load, start, end, codes):
    if not start or not end:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    selected = codes or _ALL_NSE_CODES
    try:
        df = _load_archive_range(selected, start, end)
    except Exception as e:
        return (
            html.Div(f"Error loading data: {e}",
                     style=dict(color=C["sell"], padding="24px")),
            {}, _CHART_HIDDEN, _EXPORT_HIDDEN,
        )

    if df.empty:
        return (
            html.Div("No records found for this selection.",
                     style=dict(color=C["muted"], padding="48px 24px", textAlign="center")),
            {}, _CHART_HIDDEN, _EXPORT_HIDDEN,
        )

    records = df.assign(_dt=df["_dt"].astype(str)).to_dict("records")
    return _render_results(df), records, _CHART_VISIBLE, _EXPORT_VISIBLE


@app.callback(
    Output("explorer-chart-type",    "data"),
    Output("explorer-toggle-line",   "style"),
    Output("explorer-toggle-candle", "style"),
    Input("explorer-toggle-line",   "n_clicks"),
    Input("explorer-toggle-candle", "n_clicks"),
    prevent_initial_call=True,
)
def explorer_chart_toggle(_n_line, _n_candle):
    if ctx.triggered_id == "explorer-toggle-candle":
        return "candlestick", _LINE_INACTIVE, _CANDLE_ACTIVE
    return "line", _LINE_ACTIVE, _CANDLE_INACTIVE


@app.callback(
    Output("explorer-chart", "figure"),
    Input("explorer-data",       "data"),
    Input("explorer-chart-type", "data"),
    prevent_initial_call=True,
)
def explorer_draw_chart(records, chart_type):
    if not records:
        return go.Figure()
    df = pd.DataFrame(records)
    df["_dt"] = pd.to_datetime(df["_dt"])
    return _build_chart(df, chart_type or "line")


@app.callback(
    Output("explorer-download-csv", "data"),
    Input("explorer-dl-csv", "n_clicks"),
    State("explorer-data", "data"),
    prevent_initial_call=True,
)
def explorer_dl_csv(n, records):
    if not n or not records:
        return dash.no_update
    df = pd.DataFrame(records)
    cols = [c for c in _NSE_COLS_ORDERED if c in df.columns]
    return dcc.send_data_frame(df[cols].to_csv, "nse_data.csv", index=False)


@app.callback(
    Output("explorer-download-excel", "data"),
    Input("explorer-dl-excel", "n_clicks"),
    State("explorer-data", "data"),
    prevent_initial_call=True,
)
def explorer_dl_excel(n, records):
    if not n or not records:
        return dash.no_update
    import io
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    df = pd.DataFrame(records)
    cols = [c for c in _NSE_COLS_ORDERED if c in df.columns]
    df = df[cols]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="NSE Data", index=False)
        ws = writer.sheets["NSE Data"]

        # Style header row
        header_fill = PatternFill("solid", fgColor="0D1117")
        accent_font = Font(bold=True, color="38BDF8")
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = accent_font
            cell.alignment = Alignment(horizontal="center")

        # Auto-fit column widths
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=8)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    buf.seek(0)
    return dcc.send_bytes(buf.read, "nse_data.xlsx")


# ── run_quick_fn ──────────────────────────────────────────────────────────────
def run_quick_fn(df_clean, ticker):
    from src.analysis.returns import daily_return_analysis
    from src.analysis.moving_averages import compute_moving_averages
    from src.analysis.risk import value_at_risk
    from src.features.engineer import build_feature_matrix, select_top_features
    from src.models.xgboost_model import train_xgboost, save_xgboost
    from src.models.ensemble import generate_signal
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    ret_df, _ = daily_return_analysis(df_clean)
    ma_df = compute_moving_averages(ret_df)
    var_r = value_at_risk(df_clean, investment=DEFAULT_INVESTMENT, confidence=DEFAULT_CONFIDENCE)
    feat  = build_feature_matrix(ma_df)
    fcols = select_top_features(feat)
    model, _, actuals, preds = train_xgboost(feat, fcols)
    save_xgboost(model, ticker)
    curr  = float(df_clean["Close"].iloc[-1])
    var_p = var_r["historical_var_pct"]
    sig   = generate_signal(curr, float(preds[-1]), var_p)
    rmse  = float(np.sqrt(mean_squared_error(actuals, preds)))
    mape  = float(np.mean(np.abs((actuals-preds)/np.where(actuals==0,1,actuals)))*100)
    dacc  = float(np.mean(np.sign(np.diff(actuals))==np.sign(np.diff(preds)))*100)
    result = {**sig, "metrics": dict(rmse=rmse, mape=mape, directional_accuracy=dacc),
              "actuals": actuals.tolist(), "preds": preds.tolist(), "ma_df": ma_df}
    from main import _save_signal
    _save_signal(ticker, {k:v for k,v in result.items() if k != "ma_df"})
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="NSE Market Intelligence Platform")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Host to bind (use 0.0.0.0 for network access)")
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()
    app.run(debug=False, host=args.host, port=args.port)


