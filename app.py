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
COMPANIES = {
    "SCOM.NR": dict(name="Safaricom",               short="SCOM", sector="Telecom",   color="#38bdf8", icon="📱"),
    "EQTY.NR": dict(name="Equity Bank",             short="EQTY", sector="Banking",   color="#a78bfa", icon="🏦"),
    "KCB.NR":  dict(name="KCB Group",               short="KCB",  sector="Banking",   color="#f472b6", icon="🏦"),
    "EABL.NR": dict(name="East African Breweries",  short="EABL", sector="Beverages", color="#fb923c", icon="🍺"),
    "COOP.NR": dict(name="Co-operative Bank",       short="COOP", sector="Banking",   color="#34d399", icon="🏦"),
}
SECTORS = {
    "All Companies": list(COMPANIES.keys()),
    "Banking":       ["EQTY.NR","KCB.NR","COOP.NR"],
    "Telecom":       ["SCOM.NR"],
    "Beverages":     ["EABL.NR"],
}
PERIODS = {"1 Month":30,"3 Months":90,"6 Months":180,"1 Year":252,"3 Years":756,"All Time":9999}

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
        fill="tozeroy", fillcolor=color.replace(")", ",0.08)").replace("rgb","rgba") if "rgb" in color else color+"18",
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


def chart_comparison_indexed(tickers, days=252):
    fig = go.Figure()
    for t in tickers:
        df = load_df(t)
        if df is None or len(df) < 2: continue
        meta = COMPANIES.get(t, {})
        sub = df["Close"].tail(min(days, len(df)))
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


def chart_performance_ranked(days=252):
    rows = []
    for t, meta in COMPANIES.items():
        df = load_df(t)
        if df is None: continue
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
    fig.update_layout(**CHART_BASE, height=280,
                      title=dict(text="Which company performed best?", font=dict(color=C["accent"])),
                      xaxis_title="Price Change (%)", showlegend=False,
                      margin=dict(l=160, r=10, t=40, b=10))
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
    fig.update_layout(**CHART_BASE, height=380,
                      title=dict(text=f"{meta.get('name',ticker)} — Monthly Returns Calendar",
                                 font=dict(color=meta.get("color", C["accent"]))),
                      margin=dict(l=50, r=80, t=40, b=10))
    return fig


def chart_all_prices(tickers, days=252):
    fig = make_subplots(
        rows=len(tickers), cols=1, shared_xaxes=True,
        subplot_titles=[COMPANIES.get(t,{}).get("name",t) for t in tickers],
        vertical_spacing=0.04,
    )
    for i, t in enumerate(tickers, 1):
        df = load_df(t)
        if df is None: continue
        meta = COMPANIES.get(t, {})
        sub = df["Close"].tail(min(days, len(df)))
        fig.add_trace(go.Scatter(
            x=sub.index, y=sub.values, name=meta.get("name",t),
            line=dict(color=meta.get("color", C["accent"]), width=1.5),
            fill="tozeroy", fillcolor=meta.get("color","#fff")+"18",
            showlegend=False,
        ), row=i, col=1)
    fig.update_layout(**CHART_BASE, height=120*len(tickers)+40,
                      title=dict(text="Price History — All Companies (KES)",
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
    dcc.Store(id="pipeline-ticker",   data=""),
    dcc.Store(id="pipeline-csv-path", data=""),
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
    if tab == "analytics":  return build_analytics(astate["days"], astate["sector"], astate["heatmap"])
    if tab == "import_tab": return build_import_tab()
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
    Output("analytics-state","data"),
    Input("analytics-period","value"),
    Input("analytics-sector","value"),
    Input("heatmap-ticker","value"),
    State("analytics-state","data"),
    prevent_initial_call=True,
)
def save_analytics_state(days, sector, heatmap, state):
    s = state or {}
    if days:    s["days"]    = days
    if sector:  s["sector"]  = sector
    if heatmap: s["heatmap"] = heatmap
    return s

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
def build_analytics(days=252, sector="All Companies", heatmap_ticker="SCOM.NR"):
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
                             options=[{"label":COMPANIES[t]["name"],"value":t} for t in NSE_TICKERS],
                             value=heatmap_ticker, clearable=False,
                             style=dict(background=C["card"], width="220px", fontSize="0.82rem")),
            ]),
        ], style=dict(display="flex", gap="20px", flexWrap="wrap",
                      padding="0 24px 14px",
                      borderBottom=f"1px solid {C['border']}")),

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
    prevent_initial_call=True,
)
def update_analytics_charts(days, sector):
    tickers = SECTORS.get(sector, NSE_TICKERS)
    return (
        chart_comparison_indexed(tickers, days),
        chart_performance_ranked(days),
        chart_all_prices(tickers, days),
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
    app.run(debug=False, host="127.0.0.1", port=8050)
