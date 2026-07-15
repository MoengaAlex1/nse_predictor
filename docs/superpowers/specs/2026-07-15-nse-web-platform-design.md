# NSE Market Intelligence Platform — Web Architecture Design

**Date:** 2026-07-15  
**Status:** Approved  
**Author:** Alex Moenga  

---

## 1. Overview

Rearchitect the NSE Stock Prediction System from a local Dash app into a production web platform covering all 70 NSE-listed companies. The platform serves both retail investors (plain-language signals and guidance) and financial professionals (deep technical analysis). It is designed as a portfolio project and built for scalability — adding companies, models, and features requires minimal structural change.

**Primary user goal:** Visit a company page and walk away knowing whether to buy, hold, or sell — backed by historical analysis, ML predictions, and risk metrics.

**Stack:** React/Vite → Cloudflare Pages · Firebase (Firestore + Auth + Storage) · GitHub (code + CI/CD) · Python ML pipeline via GitHub Actions

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    GITHUB REPOSITORY                    │
│  /frontend   (React/Vite/TypeScript)                   │
│  /pipeline   (Python ML — existing src/ code reused)   │
│  /functions  (Firebase Cloud Functions, future)        │
└──────────────┬──────────────────────────────────────────┘
               │ push to main
               ▼
┌─────────────────────────┐    ┌──────────────────────────┐
│   CLOUDFLARE PAGES      │    │   GITHUB ACTIONS          │
│   Auto-deploy frontend  │    │   Cron: daily 18:00 EAT  │
│   Global CDN + HTTPS    │    │   Weekly: 02:00 EAT Sun  │
└────────────┬────────────┘    └────────────┬─────────────┘
             │  reads                        │ writes
             ▼                              ▼
┌─────────────────────────────────────────────────────────┐
│                      FIREBASE                           │
│  Firestore  — snapshots, signals, predictions, market   │
│  Auth       — Google + email/password                   │
│  Storage    — model .pt/.pkl files, raw CSVs            │
└─────────────────────────────────────────────────────────┘
```

**Three responsibilities:**
- **GitHub** — source of truth for code; triggers all automation
- **Cloudflare Pages** — serves the React SPA globally; auto-deploys on push to main
- **Firebase** — owns all runtime data, authentication, and model artifacts

The Python ML pipeline (existing `src/` directory) runs inside GitHub Actions runners. No rewrite of ML code — it is wrapped in CI jobs that invoke the existing modules.

---

## 3. Firestore Data Schema

```
companies/{ticker}                              ← public read
  name, short, sector, color, icon, description
  website, listed_year
  current_price, change_pct_today              ← updated by daily pipeline
  signal                                       ← "BUY" | "HOLD" | "SELL" (public label only)
  price_preview                                ← float[30] last 30 closing prices (public sparkline)
  last_updated

companies/{ticker}/snapshots/{YYYY-MM-DD}
  signal                  "BUY" | "HOLD" | "SELL"
  risk_adjusted_signal    "BUY" | "HOLD" | "SELL"
  current_price_KES       float
  predicted_price_KES     float
  predicted_change_pct    float
  var_95_pct              float
  rationale               string
  metrics                 { rmse, mae, mape, directional_accuracy }
  actuals                 float[]   — last 500 trading days
  preds                   float[]   — model output for same window
  forecast                float[]   — 30-day forward prediction

companies/{ticker}/technicals/{YYYY-MM-DD}
  rsi_14, macd, macd_signal, macd_hist
  bb_upper, bb_mid, bb_lower
  sma_20, sma_50, sma_200
  ema_12, ema_26
  volume, avg_volume_30d
  daily_return, volatility_30d
  monthly_heatmap         { "YYYY-MM": float, ... }

market/overview/{YYYY-MM-DD}
  top_gainers             { ticker, change_pct }[]
  top_losers              { ticker, change_pct }[]
  sector_performance      { sector: float }
  nse20_value             float
  nse20_change_pct        float
  signal_distribution     { BUY: int, HOLD: int, SELL: int }

users/{uid}
  watchlist               string[]
  created_at              timestamp
  plan                    "free" | "pro"   — for future monetisation
```

**Key decisions:**
- Snapshots are **immutable daily documents** — history is append-only, never overwritten. This gives full historical model accuracy tracking at no extra cost.
- `companies/{ticker}` top-level doc holds only lightweight metadata so the companies list loads from a single small collection read.
- `market/overview/today` is one document — the home page loads from a single read.
- 70 companies × 365 days ≈ 25,500 snapshot docs/year. Firestore Spark free tier allows 50K reads/day and 20K writes/day — the pipeline writes 140 docs/day (70 × 2 collections), well within limits. Read budget is sufficient for a portfolio-scale audience; upgrade to Blaze pay-as-you-go only when traffic demands it.

---

## 4. Frontend Pages

### Public (no login required)

| Route | Content |
|---|---|
| `/` | Market overview: NSE 20 index, top 3 gainers/losers, sector heatmap, signal distribution strip |
| `/companies` | All 70 companies — searchable, filterable by sector/signal, sortable by price change/risk |
| `/company/:ticker` | Company header, signal badge, 30-day price preview, sign-in CTA |

### Gated (free Firebase account)

| Route | Content |
|---|---|
| `/company/:ticker` | Full deep dive (see below) |
| `/market` | Cross-company analytics, rankings, correlation matrix, sector comparison |
| `/login` | Firebase Auth — Google + email/password |
| `/register` | Sign up |

### Company Deep Dive — section breakdown

```
┌─ Price History ──────────────────────────────────────┐
│  Interactive chart — 1M / 3M / 6M / 1Y / 3Y / All  │
│  Toggle overlays: SMA20, SMA50, SMA200, Bollinger    │
└──────────────────────────────────────────────────────┘
┌─ AI Signal ──────────────────────────────────────────┐
│  BUY / HOLD / SELL  +  risk-adjusted signal          │
│  Plain-English rationale                             │
│  Model accuracy: MAPE, directional accuracy %        │
└──────────────────────────────────────────────────────┘
┌─ Price Prediction ───────────────────────────────────┐
│  Actual vs Predicted (historical backtest chart)     │
│  30-day forward forecast with confidence band        │
└──────────────────────────────────────────────────────┘
┌─ Technical Indicators ───────────────────────────────┐
│  RSI gauge, MACD chart, Bollinger Band chart         │
└──────────────────────────────────────────────────────┘
┌─ Returns & Risk ─────────────────────────────────────┐
│  Daily/monthly returns, annualised volatility        │
│  Value at Risk (95%), monthly performance heatmap    │
└──────────────────────────────────────────────────────┘
┌─ vs Market ──────────────────────────────────────────┐
│  Performance vs NSE 20 index                         │
│  Correlation with sector peers                       │
└──────────────────────────────────────────────────────┘
```

### Gating pattern

```tsx
<AuthGuard fallback={<SignInPrompt />}>
  <PredictionChart data={snapshot} />
  <TechnicalsPanel data={technicals} />
</AuthGuard>
```

`SignInPrompt` renders a blurred content preview with a "Sign in free to unlock" overlay. The public teaser is always rendered behind it — visible but unreadable — to communicate value before asking for login.

### Responsive layout

- **Mobile:** Single column, tab navigation between sections on the deep dive page
- **Tablet:** Two-column card grid, full-width charts
- **Desktop:** Sidebar navigation, three-column analytics grid

---

## 5. Frontend Tech Stack

| Tool | Purpose |
|---|---|
| React 18 + TypeScript | Component framework |
| Vite | Build tool — fast, Cloudflare Pages native |
| Tailwind CSS | Styling — dark theme by default, responsive |
| Recharts | Charts — lightweight, composable, React-native |
| Firebase JS SDK v10 | Firestore reads + Auth |
| React Router v6 | Client-side routing |
| Zustand | Global state: auth user, selected ticker |
| TanStack Query | Firestore fetching, caching, loading/error states |

### Project structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/           — Button, Badge, Card, Spinner, Modal
│   │   ├── charts/       — PriceChart, PredictionChart, MacdChart,
│   │   │                   RsiGauge, HeatmapGrid, SparkLine
│   │   ├── company/      — SignalCard, TechnicalsPanel, ReturnsPanel,
│   │   │                   VsMarketPanel, ForecastPanel
│   │   ├── market/       — OverviewStrip, SectorHeatmap, RankingChart,
│   │   │                   CorrelationMatrix
│   │   └── layout/       — Navbar, Footer, AuthGuard, PageShell
│   ├── pages/
│   │   ├── Home.tsx
│   │   ├── Companies.tsx
│   │   ├── CompanyDeepDive.tsx
│   │   ├── MarketAnalytics.tsx
│   │   ├── Login.tsx
│   │   └── Register.tsx
│   ├── hooks/
│   │   ├── useCompany.ts     — companies/{ticker} + latest snapshot
│   │   ├── useSnapshot.ts    — snapshot by date
│   │   ├── useMarket.ts      — market/overview/today
│   │   └── useWatchlist.ts   — users/{uid}/watchlist read/write
│   ├── lib/
│   │   ├── firebase.ts       — Firebase app init
│   │   ├── firestore.ts      — typed Firestore query helpers
│   │   └── auth.ts           — login, logout, onAuthStateChanged
│   ├── store/
│   │   └── useAuthStore.ts   — Zustand: user, loading, error
│   └── types/
│       └── index.ts          — CompanyDoc, SnapshotDoc, MarketDoc
├── public/
│   └── nse-logos/            — company logo PNGs
├── index.html
├── vite.config.ts
└── tailwind.config.ts
```

---

## 6. ML Pipeline & GitHub Actions

### Workflow 1: Daily Inference

```yaml
# .github/workflows/daily_inference.yml
trigger: cron "0 15 * * 1-5"   # 15:00 UTC = 18:00 EAT, Mon–Fri

steps:
  1. Checkout repo
  2. Set up Python 3.11
  3. pip install -r pipeline/requirements.txt
  4. Download saved models from Firebase Storage → /tmp/models/
  5. Download latest CSVs from Firebase Storage → /tmp/data/
  6. For each of 70 companies (4 parallel workers):
       a. clean_ohlcv()
       b. build_feature_matrix()
       c. Load model → LSTM + XGBoost + ARIMA inference
       d. ensemble_predict() → signal → 30-day forecast
       e. Compute technicals (RSI, MACD, Bollinger, MAs)
       f. Compute VaR, returns, monthly heatmap
       g. Write snapshot + technicals docs to Firestore
  7. Aggregate → write market/overview/today to Firestore
  8. On failure → GitHub notification

# Estimated runtime: 25–35 min for 70 companies
# Cost: free (GitHub Actions 2000 min/month free tier)
```

### Workflow 2: Weekly Model Training

```yaml
# .github/workflows/weekly_training.yml
trigger: cron "0 23 * * 0"     # 23:00 UTC Sat = 02:00 EAT Sun

steps:
  1. Same setup as daily
  2. Download all historical CSVs from Firebase Storage
  3. For each company (sequential — memory-intensive):
       a. Full LSTM training (PyTorch)
       b. Full XGBoost training
       c. Full ARIMA fit
       d. Evaluate ensemble metrics
       e. Save .pt, .pkl, scaler → Firebase Storage
  4. Log training metrics to Firestore models/{ticker}/training_runs/

# Estimated runtime: 3–4 hrs for 70 companies
# Cost: free (~240 min/week, within free tier)
```

### Workflow 3: Frontend Deploy

```yaml
# .github/workflows/deploy.yml
trigger: push to main, path: frontend/**

steps:
  1. npm ci → npm run build
  2. Deploy to Cloudflare Pages via Wrangler

# Runtime: ~2 min
```

### Data ingestion

yfinance does not carry `.NR` tickers. Two modes, switchable via config:

- **Mode 1 (current):** CSVs committed to `pipeline/data/raw/` — version-controlled, updated manually or via script
- **Mode 2 (future plug-in):** `pipeline/scraper/nse_scraper.py` fetches fresh CSVs from `nse.co.ke` and uploads to Firebase Storage before inference runs

The pipeline reads from a configurable source path — switching modes requires one config change, no structural change.

---

## 7. Authentication & Access Control

| Content | Public | Logged-in (free) |
|---|---|---|
| Company list (70) | Full | Full |
| Home market overview | Full | Full |
| Company header + signal badge | Full | Full |
| 30-day price preview | Full | Full |
| Full price history + overlays | Blurred teaser | Unlocked |
| AI prediction chart + forecast | Blurred teaser | Unlocked |
| Technical indicators | Blurred teaser | Unlocked |
| Returns & risk analysis | Blurred teaser | Unlocked |
| vs Market comparison | Blurred teaser | Unlocked |
| Market analytics page | — | Unlocked |
| Watchlist | — | Unlocked |

Firebase Auth providers: Google OAuth + email/password. User document created in Firestore on first login.

---

## 8. Scalability Plug-in Points

| Future feature | What changes |
|---|---|
| Add a company | Add to `companies.json` + drop CSV in `data/raw/` |
| Add a new model | Add `src/models/new_model.py`, register in `ensemble.py` |
| Live NSE data scraping | Add `pipeline/scraper/nse_scraper.py`, wire into daily workflow Step 1 |
| Price alerts | Firebase Cloud Function `onWrite` on snapshot doc → email/push |
| Public REST API | Cloudflare Worker in front of Firestore — no pipeline or frontend change |
| More markets (Uganda, Tanzania) | Add `exchange` field to company schema + exchange filter on frontend |
| Pro tier / monetisation | Add `users/{uid}/plan` field + Stripe Firebase Extension |
| Portfolio tracker | Add `users/{uid}/holdings` collection + new frontend page |

---

## 9. Repo Structure

```
nse_predictor/                  ← existing repo root
├── frontend/                   ← new: React/Vite app
├── pipeline/                   ← renamed from src/ + scripts
│   ├── src/                    ← existing ML modules (reused as-is)
│   ├── data/
│   │   ├── raw/                ← NSE CSVs (70 companies)
│   │   └── cleaned/            ← pipeline output (gitignored)
│   ├── config/
│   │   └── companies.json      ← all 70 companies + metadata
│   ├── scripts/
│   │   ├── run_inference.py    ← daily job entry point
│   │   ├── run_training.py     ← weekly job entry point
│   │   └── push_to_firestore.py
│   └── requirements.txt
├── .github/
│   └── workflows/
│       ├── daily_inference.yml
│       ├── weekly_training.yml
│       └── deploy.yml
├── docs/
│   └── superpowers/specs/
│       └── 2026-07-15-nse-web-platform-design.md
├── .gitignore
└── README.md
```

---

## 10. Environment Variables & Secrets

### GitHub Actions secrets
```
FIREBASE_SERVICE_ACCOUNT_JSON   — service account for Firestore + Storage writes
CLOUDFLARE_API_TOKEN            — for Wrangler deployment
CLOUDFLARE_ACCOUNT_ID
```

### Frontend (Cloudflare Pages environment variables)
```
VITE_FIREBASE_API_KEY
VITE_FIREBASE_AUTH_DOMAIN
VITE_FIREBASE_PROJECT_ID
VITE_FIREBASE_STORAGE_BUCKET
VITE_FIREBASE_MESSAGING_SENDER_ID
VITE_FIREBASE_APP_ID
```

Firebase client keys are safe to expose in frontend code — access is controlled by Firestore Security Rules, not by keeping keys secret.

---

## 11. Firestore Security Rules

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Companies list and metadata — public read
    // Top-level doc includes signal label + price_preview for public teaser
    match /companies/{ticker} {
      allow read: if true;
      allow write: if false;  // pipeline writes via service account only
    }

    // Snapshots and technicals — logged-in users only
    match /companies/{ticker}/snapshots/{date} {
      allow read: if request.auth != null;
      allow write: if false;
    }
    match /companies/{ticker}/technicals/{date} {
      allow read: if request.auth != null;
      allow write: if false;
    }

    // Market overview — public read
    match /market/{doc}/{date} {
      allow read: if true;
      allow write: if false;
    }

    // User data — owner only
    match /users/{uid} {
      allow read, write: if request.auth != null && request.auth.uid == uid;
    }
  }
}
```

---

## Summary

| Decision | Choice |
|---|---|
| Frontend | React 18 + TypeScript + Vite + Tailwind + Recharts |
| Hosting | Cloudflare Pages (auto-deploy from GitHub) |
| Database | Firebase Firestore (daily immutable snapshots) |
| Auth | Firebase Auth — Google + email/password |
| Model storage | Firebase Storage (.pt, .pkl, scaler files) |
| ML pipeline | GitHub Actions — daily inference (18:00 EAT) + weekly training (Sun 02:00 EAT) |
| Companies | All 70 NSE-listed, config-driven |
| Access model | Public preview → free account → full analysis |
| Scalability | Config-driven, plug-in model interface, Cloud Functions ready |
