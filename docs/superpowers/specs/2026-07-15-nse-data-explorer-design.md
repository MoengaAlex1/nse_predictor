# NSE Data Explorer — Professional Redesign

**Date:** 2026-07-15  
**Project:** C:\Users\moeng\nse_predictor

## Goal
Elevate the Data Explorer tab into a professional financial data terminal: guided UI, candlestick/line toggle chart with volume, summary stats, top movers strip, Excel + CSV export, and a one-click `.bat` launcher accessible on the local network.

## Architecture
- Single `app.py` — no new app files
- `launch.bat` — double-click launcher; binds server to `0.0.0.0:8050` (local network accessible), auto-opens browser
- `app.py` accepts `--host` and `--port` CLI args

## Data Explorer Tab Layout (top → bottom)
1. **Collapsible guidance panel** — data coverage dates, field glossary (all 13 NSE columns explained), quick-start steps
2. **Sticky controls bar** — date range picker (min: Jan 2007, max: latest archive date), company multi-select (62 codes + full names), chart toggle pill (Candlestick | Line), Load Data button
3. **Summary stats strip** (post-load) — Best Performer %, Worst Performer %, Biggest Single-Day Move, Total Records
4. **Top Movers bar** — top 3 gainers (green) + top 3 losers (red) with ticker + % for selected period
5. **Chart** — candlestick (OHLC) or line, with volume subplot underneath; toggle switches instantly
6. **Data table** — all 13 NSE columns, 100 rows/page, sortable, filterable, Change/Change% colour-coded
7. **Export bar** — Download CSV + Download Excel (.xlsx)

## Key Callbacks
- `explorer_load` — loads archive data, computes stats + movers, stores in `dcc.Store`
- `explorer_chart_toggle` — updates `explorer-chart-type` store on toggle click
- `explorer_update_chart` — re-renders chart figure from stored data + chart type
- `explorer_download_csv` — CSV export
- `explorer_download_excel` — Excel .xlsx export via openpyxl
