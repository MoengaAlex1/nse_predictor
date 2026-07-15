"""
NSE Market Dashboard — plain-language stock analysis for everyday investors.
Run:  python app.py   →   open http://127.0.0.1:8050
"""
import sys, io, json, base64
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

from config import (NSE_TICKERS, DATA_CLEANED, DATA_FEATURES,
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

def company_card(ticker):
    meta = COMPANIES[ticker]
    df   = load_df(ticker)
    sig  = load_sig(ticker)
    if df is None:
        return html.Div()
    last  = float(df["Close"].iloc[-1])
    prev  = float(df["Close"].iloc[-2]) if len(df)>1 else last
    chg   = (last-prev)/prev*100
    chg_c = C["buy"] if chg>=0 else C["sell"]
    signal = sig.get("signal","—") if sig else "—"
    ra_sig = sig.get("risk_adjusted_signal","—") if sig else "—"
    rlabel, rcolor = risk_label(sig.get("var_95_pct",0) if sig else 0)
    acc = sig["metrics"]["directional_accuracy"] if sig and sig.get("metrics") else None

    return html.Div([
        # header row
        html.Div([
            html.Div([
                html.Span(meta["icon"], style=dict(fontSize="1.4rem")),
            ], style=dict(background=meta["color"]+"22", borderRadius="50%",
                          width="42px", height="42px", display="flex",
                          alignItems="center", justifyContent="center")),
            html.Div([
                html.Div(meta["name"], style=dict(fontWeight=700, fontSize="0.92rem",
                                                  color=C["text"])),
                html.Span(meta["sector"], style=dict(fontSize="0.65rem", color=meta["color"],
                                                     background=meta["color"]+"22",
                                                     padding="1px 7px", borderRadius="10px")),
            ]),
        ], style=dict(display="flex", gap="10px", alignItems="center", marginBottom="12px")),
        # price row
        html.Div([
            html.Span(f"KES {last:,.2f}", style=dict(fontWeight=800, fontSize="1.15rem")),
            html.Span(f"{chg:+.2f}% today", style=dict(color=chg_c, fontSize="0.78rem",
                                                         fontWeight=600, marginLeft="8px")),
        ], style=dict(marginBottom="10px")),
        # recommendation
        html.Div([
            html.Div("Our advice:", style=dict(fontSize="0.65rem", color=C["muted"],
                                                marginBottom="4px")),
            advice_badge(ra_sig, "md"),
        ], style=dict(marginBottom="10px")),
        # mini stats
        html.Div([
            stat_pill("Risk level", rlabel, rcolor),
            stat_pill("AI accuracy", f"{acc:.0f}%" if acc else "—", C["accent"]),
            stat_pill("1-Year change", f"{pct_change_over(df,252):+.1f}%",
                      C["buy"] if pct_change_over(df,252)>=0 else C["sell"]),
        ], style=dict(display="flex", gap="6px", flexWrap="wrap")),
    ], id={"type":"company-card","index":ticker}, n_clicks=0,
       style=dict(background=C["card"], border=f"1px solid {C['border']}",
                  borderRadius="10px", padding="16px", cursor="pointer",
                  transition="border 0.15s",
    ))

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
            dcc.Upload(id="csv-upload", children=html.Button(
                "⬆ Import Daily Prices", style=dict(
                    background="transparent", color=C["accent"], fontWeight=600,
                    border=f"1px solid {C['accent']}", borderRadius="20px",
                    padding="7px 16px", cursor="pointer", fontSize="0.82rem")),
                accept=".csv"),
        ], style=dict(display="flex", gap="10px", alignItems="center")),
    ], style=dict(background=C["header"], borderBottom=f"1px solid {C['border']}",
                  padding="12px 24px", display="flex",
                  justifyContent="space-between", alignItems="center")),

    # ── CSV import bar (hidden until upload) ─────────────────────────────────
    html.Div(id="import-bar", children=[
        html.Span("📂 File loaded. Enter a name for this company:",
                  style=dict(color=C["muted"], fontSize="0.83rem")),
        dcc.Input(id="csv-company-name", placeholder="e.g. BAMB.NR",
                  style=dict(background=C["card"], border=f"1px solid {C['accent']}",
                             color=C["text"], borderRadius="6px",
                             padding="5px 12px", width="180px", fontSize="0.83rem")),
        html.Button("Run Analysis", id="run-import-btn", style=dict(
            background=C["accent"], color=C["header"], fontWeight=700,
            border="none", borderRadius="6px", padding="5px 16px", cursor="pointer")),
        dcc.Loading(html.Span(id="import-status"), type="circle", color=C["accent"]),
    ], style=dict(display="none", gap="12px", alignItems="center",
                  padding="8px 24px", background=C["panel"],
                  borderBottom=f"1px solid {C['border']}")),

    # ── Main tabs ─────────────────────────────────────────────────────────────
    dcc.Tabs(id="main-tabs", value="overview", children=[
        dcc.Tab(label="🏠  Overview",   value="overview",  style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label="🔍  Company",    value="company",   style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label="📊  Analytics",  value="analytics", style=TAB_STYLE, selected_style=TAB_SELECTED),
        dcc.Tab(label="📥  Import",     value="import_tab",style=TAB_STYLE, selected_style=TAB_SELECTED),
    ], style=dict(background=C["panel"], borderBottom=f"1px solid {C['border']}")),

    dcc.Loading(html.Div(id="tab-content"), type="dot", color=C["accent"]),

], style=dict(background=C["bg"], color=C["text"], minHeight="100vh",
              fontFamily="'Inter','Segoe UI',sans-serif", margin=0, padding=0))

# ── Tab content router ────────────────────────────────────────────────────────
@app.callback(Output("tab-content","children"),
              Input("main-tabs","value"),
              Input("selected-ticker","data"),
              Input("analysis-store","data"))
def render_tab(tab, ticker, store):
    if tab == "overview":   return build_overview()
    if tab == "company":    return build_company(ticker, store)
    if tab == "analytics":  return build_analytics()
    if tab == "import_tab": return build_import_tab()
    return html.Div()

# ── OVERVIEW ─────────────────────────────────────────────────────────────────
def build_overview():
    sector_btns = [
        html.Button(s, id={"type":"sector-btn","index":s},
                    n_clicks=0, style=dict(
                        background=C["card"] if s != "All Companies" else C["accent"],
                        color=C["header"] if s != "All Companies" else C["header"],
                        border=f"1px solid {C['border']}", borderRadius="20px",
                        padding="5px 14px", cursor="pointer", fontSize="0.8rem",
                        fontWeight=600, marginRight="6px"))
        for s in SECTORS
    ]
    cards = [html.Div(company_card(t), style=dict(flex="1 1 300px", maxWidth="380px"))
             for t in NSE_TICKERS]
    return html.Div([
        # intro banner
        html.Div([
            html.Div("What should I do with my money?", style=dict(
                fontSize="1.3rem", fontWeight=800, color=C["text"], marginBottom="4px")),
            html.Div("Our AI system analyses each company's stock price history and gives you a simple recommendation.",
                     style=dict(fontSize="0.85rem", color=C["muted"])),
        ], style=dict(padding="20px 24px 12px", borderBottom=f"1px solid {C['border']}")),
        # sector filter
        html.Div([html.Span("Filter by sector: ", style=dict(color=C["muted"], fontSize="0.82rem",
                                                              marginRight="8px"))] + sector_btns,
                 style=dict(padding="12px 24px", display="flex", alignItems="center",
                            flexWrap="wrap")),
        # company cards grid
        html.Div(cards, id="cards-grid", style=dict(
            display="flex", flexWrap="wrap", gap="16px", padding="0 24px 24px")),
        # legend
        html.Div([
            html.Div("How to read the recommendations:", style=dict(
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
    ])

# ── COMPANY DETAIL ────────────────────────────────────────────────────────────
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

                    # AI reasoning
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
                    html.Button("🔄 Update Analysis",id="quick-btn",style=dict(
                        background=C["accent"],color=C["header"],fontWeight=700,
                        border="none",borderRadius="20px",padding="7px 20px",
                        cursor="pointer",fontSize="0.83rem",marginTop="14px")),
                    dcc.Loading(html.Span(id="quick-status"),type="circle",color=C["accent"]),
                ],style=dict(display="flex",alignItems="center",gap="12px")),

            ], style=dict(padding="20px 24px",
                          borderBottom=f"1px solid {C['border']}")),

            # Price chart
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

# ── ANALYTICS ─────────────────────────────────────────────────────────────────
def build_analytics():
    return html.Div([
        html.Div([
            html.Div("📊  Historical Data & Comparisons",
                     style=dict(fontSize="1.15rem", fontWeight=800, color=C["text"])),
            html.Div("Compare how each company's stock price has changed over time.",
                     style=dict(fontSize="0.83rem", color=C["muted"], marginTop="2px")),
        ], style=dict(padding="18px 24px 10px")),

        # Controls row
        html.Div([
            html.Div([
                html.Label("Period:", style=dict(color=C["muted"], fontSize="0.8rem",
                                                  marginBottom="4px")),
                dcc.Dropdown(id="analytics-period",
                             options=[{"label":k,"value":v} for k,v in PERIODS.items()],
                             value=252, clearable=False,
                             style=dict(background=C["card"], width="160px", fontSize="0.82rem")),
            ]),
            html.Div([
                html.Label("Group:", style=dict(color=C["muted"], fontSize="0.8rem",
                                                marginBottom="4px")),
                dcc.Dropdown(id="analytics-sector",
                             options=[{"label":k,"value":k} for k in SECTORS],
                             value="All Companies", clearable=False,
                             style=dict(background=C["card"], width="180px", fontSize="0.82rem")),
            ]),
            html.Div([
                html.Label("Calendar view:", style=dict(color=C["muted"], fontSize="0.8rem",
                                                         marginBottom="4px")),
                dcc.Dropdown(id="heatmap-ticker",
                             options=[{"label":COMPANIES[t]["name"],"value":t} for t in NSE_TICKERS],
                             value="SCOM.NR", clearable=False,
                             style=dict(background=C["card"], width="220px", fontSize="0.82rem")),
            ]),
        ], style=dict(display="flex", gap="20px", flexWrap="wrap",
                      padding="0 24px 14px",
                      borderBottom=f"1px solid {C['border']}")),

        # Charts grid
        html.Div([
            # Row 1: indexed growth + ranked bar
            html.Div([
                html.Div([
                    html.Div("💰 Growth of KES 100 invested", style=dict(
                        fontWeight=700, fontSize="0.88rem", color=C["text"],
                        marginBottom="4px")),
                    html.Div("Starts everyone at the same point — easy to compare who grew more.",
                             style=dict(fontSize="0.72rem", color=C["muted"], marginBottom="8px")),
                    dcc.Graph(id="chart-indexed", config=dict(displayModeBar=False)),
                ], style=dict(flex="2", background=C["card"],
                              border=f"1px solid {C['border']}", borderRadius="10px",
                              padding="16px")),
                html.Div([
                    html.Div("🏆 Best & Worst Performers", style=dict(
                        fontWeight=700, fontSize="0.88rem", color=C["text"],
                        marginBottom="4px")),
                    html.Div("Which company's price changed the most over the selected period?",
                             style=dict(fontSize="0.72rem", color=C["muted"], marginBottom="8px")),
                    dcc.Graph(id="chart-ranked", config=dict(displayModeBar=False)),
                ], style=dict(flex="1", background=C["card"],
                              border=f"1px solid {C['border']}", borderRadius="10px",
                              padding="16px")),
            ], style=dict(display="flex", gap="16px")),

            # Row 2: stacked price panels
            html.Div([
                html.Div("📉 Individual Price History", style=dict(
                    fontWeight=700, fontSize="0.88rem", color=C["text"],
                    marginBottom="4px")),
                html.Div("Actual KES price history for each company in your selected group.",
                         style=dict(fontSize="0.72rem", color=C["muted"], marginBottom="8px")),
                dcc.Graph(id="chart-all-prices", config=dict(displayModeBar=True, scrollZoom=True)),
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
                dcc.Graph(id="chart-heatmap", config=dict(displayModeBar=False)),
            ], style=dict(background=C["card"], border=f"1px solid {C['border']}",
                          borderRadius="10px", padding="16px")),

            # Row 4: summary table
            html.Div([
                html.Div("📋 Performance Summary Table", style=dict(
                    fontWeight=700, fontSize="0.88rem", color=C["text"],
                    marginBottom="8px")),
                html.Div(id="summary-table"),
            ], style=dict(background=C["card"], border=f"1px solid {C['border']}",
                          borderRadius="10px", padding="16px")),

        ], style=dict(display="flex", flexDirection="column",
                      gap="16px", padding="16px 24px 24px")),
    ], style=dict(overflowY="auto", maxHeight="calc(100vh - 105px)"))

# ── IMPORT TAB ────────────────────────────────────────────────────────────────
def build_import_tab():
    return html.Div([
        html.Div([
            html.Div("📥  Import Daily Price Data", style=dict(
                fontSize="1.15rem", fontWeight=800, color=C["text"])),
            html.Div("Have a CSV file of daily stock prices? Upload it here and we'll analyse it for you.",
                     style=dict(fontSize="0.83rem", color=C["muted"], marginTop="2px")),
        ], style=dict(padding="20px 24px 16px")),

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
                ], style=dict(textAlign="center", padding="40px")),
                style=dict(border=f"2px dashed {C['border']}", borderRadius="12px",
                           background=C["card"], cursor="pointer", marginBottom="16px",
                           transition="border 0.2s"),
            ),
            # Company name + run
            html.Div([
                html.Label("Company ticker / name:", style=dict(color=C["muted"],
                                                                fontSize="0.82rem")),
                dcc.Input(id="import-tab-name", placeholder="e.g. BAMB.NR or UCHUMI.NR",
                          style=dict(background=C["card"], border=f"1px solid {C['border']}",
                                     color=C["text"], borderRadius="8px",
                                     padding="8px 14px", width="260px")),
                html.Button("Run Analysis", id="run-import-tab-btn", style=dict(
                    background=C["accent"], color=C["header"], fontWeight=700,
                    border="none", borderRadius="8px",
                    padding="8px 20px", cursor="pointer", fontSize="0.88rem")),
                dcc.Loading(html.Div(id="import-tab-status"), type="circle", color=C["accent"]),
            ], style=dict(display="flex", gap="12px", alignItems="flex-end",
                          flexWrap="wrap")),

            # Instructions
            html.Div([
                html.Div("📌 How to get NSE data:", style=dict(
                    fontWeight=700, color=C["text"], marginBottom="8px", fontSize="0.88rem")),
                html.Ol([
                    html.Li("Go to the NSE website: nse.co.ke", style=dict(fontSize="0.82rem", color=C["muted"], marginBottom="4px")),
                    html.Li("Navigate to Trade Statistics → Historical Data", style=dict(fontSize="0.82rem", color=C["muted"], marginBottom="4px")),
                    html.Li("Select your company and date range", style=dict(fontSize="0.82rem", color=C["muted"], marginBottom="4px")),
                    html.Li("Download the CSV file", style=dict(fontSize="0.82rem", color=C["muted"], marginBottom="4px")),
                    html.Li("Upload it here using the box above", style=dict(fontSize="0.82rem", color=C["muted"])),
                ]),
            ], style=dict(background=C["card"], border=f"1px solid {C['border']}",
                          borderRadius="10px", padding="16px", marginTop="16px")),

        ], style=dict(padding="0 24px 24px", maxWidth="700px")),
    ], style=dict(overflowY="auto", maxHeight="calc(100vh - 105px)"))

# ── Callbacks ─────────────────────────────────────────────────────────────────
@app.callback(
    Output("selected-ticker","data"),
    Input({"type":"sidebar-ticker","index":dash.ALL},"n_clicks"),
    Input({"type":"company-card","index":dash.ALL},"n_clicks"),
    Input("search-input","value"),
    State("selected-ticker","data"),
    prevent_initial_call=True,
)
def select_ticker(sidebar_clicks, card_clicks, search, current):
    t = ctx.triggered_id
    if isinstance(t, dict): return t["index"]
    if t == "search-input" and search:
        s = search.strip().upper()
        return s if s.endswith(".NR") else s+".NR"
    return current

@app.callback(
    Output("main-tabs","value"),
    Input({"type":"company-card","index":dash.ALL},"n_clicks"),
    prevent_initial_call=True,
)
def go_to_company(_):
    return "company"

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
    Output("chart-indexed","figure"),
    Output("chart-ranked","figure"),
    Output("chart-all-prices","figure"),
    Output("summary-table","children"),
    Input("analytics-period","value"),
    Input("analytics-sector","value"),
)
def update_analytics(days, sector):
    tickers = SECTORS.get(sector, NSE_TICKERS)
    indexed = chart_comparison_indexed(tickers, days)
    ranked  = chart_performance_ranked(days)
    prices  = chart_all_prices(tickers, days)

    # Summary table
    rows = []
    for t in tickers:
        df   = load_df(t)
        sig  = load_sig(t)
        meta = COMPANIES.get(t, {})
        if df is None: continue
        row = {
            "Company":   meta.get("name", t),
            "Sector":    meta.get("sector","—"),
            "Price (KES)": f"{float(df['Close'].iloc[-1]):,.2f}",
            "1 Month":   f"{pct_change_over(df,21):+.1f}%",
            "3 Months":  f"{pct_change_over(df,63):+.1f}%",
            "6 Months":  f"{pct_change_over(df,126):+.1f}%",
            "1 Year":    f"{pct_change_over(df,252):+.1f}%",
            "Our Advice": (sig.get("risk_adjusted_signal","—") if sig else "—"),
        }
        rows.append(row)

    if rows:
        df_tbl = pd.DataFrame(rows)
        table = dash_table.DataTable(
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
                {"if":{"filter_query":"{Our Advice} = BUY"},"color":C["buy"],"fontWeight":700},
                {"if":{"filter_query":"{Our Advice} = SELL"},"color":C["sell"],"fontWeight":700},
                {"if":{"filter_query":"{Our Advice} = HOLD"},"color":C["hold"],"fontWeight":700},
            ],
        )
    else:
        table = html.Div("No data", style=dict(color=C["muted"]))

    return indexed, ranked, prices, table

@app.callback(
    Output("chart-heatmap","figure"),
    Input("heatmap-ticker","value"),
)
def update_heatmap(ticker):
    return chart_monthly_heatmap(ticker)

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
        from app import run_quick as _rq
        result = _rq(df, ticker)
        store[ticker] = {k:v for k,v in result.items()
                         if k not in ("ma_df",) and not isinstance(v, pd.DataFrame)}
        return store, html.Span("✓ Done", style=dict(color=C["buy"], fontSize="0.8rem"))
    except Exception as e:
        return store, html.Span(f"Error: {e}", style=dict(color=C["sell"], fontSize="0.75rem"))

@app.callback(
    Output("import-bar","style"),
    Output("analysis-store","data",allow_duplicate=True),
    Input("csv-upload","contents"),
    State("analysis-store","data"),
    prevent_initial_call=True,
)
def show_import_bar(contents, store):
    if not contents: return dict(display="none"), store
    store["_csv"] = contents
    return (dict(display="flex",gap="12px",alignItems="center",
                 padding="8px 24px",background=C["panel"],
                 borderBottom=f"1px solid {C['border']}"), store)

@app.callback(
    Output("selected-ticker","data",allow_duplicate=True),
    Output("analysis-store","data",allow_duplicate=True),
    Output("import-status","children"),
    Output("main-tabs","value",allow_duplicate=True),
    Input("run-import-btn","n_clicks"),
    State("csv-company-name","value"),
    State("analysis-store","data"),
    prevent_initial_call=True,
)
def process_import(n, name, store):
    return _process_csv(n, name, store.get("_csv"), store)

@app.callback(
    Output("selected-ticker","data",allow_duplicate=True),
    Output("analysis-store","data",allow_duplicate=True),
    Output("import-tab-status","children"),
    Output("main-tabs","value",allow_duplicate=True),
    Input("run-import-tab-btn","n_clicks"),
    State("import-tab-name","value"),
    State("csv-upload-tab","contents"),
    State("analysis-store","data"),
    prevent_initial_call=True,
)
def process_import_tab(n, name, contents, store):
    return _process_csv(n, name, contents, store)

def _process_csv(n, name, contents, store):
    no = (dash.no_update, store,
          html.Span("Please fill in the company name.", style=dict(color=C["hold"])),
          dash.no_update)
    if not n or not name or not contents: return no
    ticker = name.strip().upper()
    if not ticker.endswith(".NR"): ticker += ".NR"
    try:
        _, cs = contents.split(",")
        decoded = base64.b64decode(cs)
        from src.data.fetcher import load_from_csv
        from src.data.cleaner import clean_ohlcv, save_cleaned
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as f:
            f.write(decoded); tmp = f.name
        raw = load_from_csv(tmp, ticker=ticker); os.unlink(tmp)
        cleaned, _ = clean_ohlcv(raw, ticker=ticker)
        save_cleaned(cleaned, ticker)
        result = run_quick_fn(cleaned, ticker)
        store[ticker] = {k:v for k,v in result.items()
                         if k not in ("ma_df",) and not isinstance(v, pd.DataFrame)}
        return (ticker, store,
                html.Span(f"✓ {ticker} analysed!", style=dict(color=C["buy"])),
                "company")
    except Exception as e:
        return (dash.no_update, store,
                html.Span(f"Error: {e}", style=dict(color=C["sell"], fontSize="0.75rem")),
                dash.no_update)

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
