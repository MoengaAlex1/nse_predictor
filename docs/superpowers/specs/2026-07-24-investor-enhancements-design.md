# Investor Experience Enhancements — Design Spec
**Date:** 2026-07-24  
**Status:** Approved for implementation  
**Reference:** MarketScreener stock page layout (cooperative bank page)

---

## 1. Goal

Enrich the `CompanyDeepDive` page for all 61 NSE-listed companies with four new investor-grade panels modelled after MarketScreener's design language:

1. **Company Profile Card** — About block with sector, listing info, description, website
2. **Quote Summary Panel** — Dense metrics strip: day range, 52W range slider, market cap, P/E, yield, ML model consensus bar
3. **Valuation Panel** — Tabbed multi-year fundamentals table (Valuation / Income / Dividends) with sector peer comparison
4. **News Panel** — Filterable, category-tagged announcement feed with inline expand and external link support

All four panels are independent modules that never modify existing components. Existing charts (TradingChart, PredictionChart), SnapshotCard, TechnicalsCard, FilingsTimeline, PriceExplainer, and StatsStrip are untouched.

---

## 2. Audit Trail Strategy

Every deliverable ships as its own focused git commit using the project's existing Conventional Commits convention. Each commit is self-contained and `git revert <hash>` undoes exactly that unit without touching others.

**Planned commit sequence:**

```
feat: add shares_outstanding + company profile fields to companies.json
feat: add FundamentalsDoc + NewsItem types to index.ts
feat: add fetchFundamentals() + fetchNews() to firestore.ts
feat: add useFundamentals() + useNews() hooks to useCompany.ts
feat: add CompanyProfileCard panel
feat: add QuoteSummaryPanel with 52W slider and ML consensus bar
feat: add ValuationPanel with tabbed multi-year table
feat: add NewsPanel with category filter and inline expand
feat: wire all four panels into CompanyDeepDive
feat: add Python news scraper (pipeline/scripts/scrape_news.py)
feat: add news scraper to daily_inference GitHub Actions workflow
```

---

## 3. Architecture

### 3.1 Component Map

```
frontend/src/
├── components/
│   └── investor/                     ← NEW directory
│       ├── CompanyProfileCard.tsx
│       ├── QuoteSummaryPanel.tsx
│       ├── ValuationPanel.tsx
│       └── NewsPanel.tsx
├── hooks/
│   └── useCompany.ts                 ← add useFundamentals(), useNews()
├── lib/
│   └── firestore.ts                  ← add fetchFundamentals(), fetchNews()
└── types/
    └── index.ts                      ← add FundamentalsDoc, NewsItem

pipeline/
└── scripts/
    └── scrape_news.py                ← NEW: pushes to news/{ticker}/items
```

### 3.2 Page Section Order (top → bottom in CompanyDeepDive)

```
1.  Trading terminal header      (existing — price, signal badge)
2.  CompanyProfileCard           ← NEW: inserted after header
3.  QuoteSummaryPanel            ← NEW: inserted after profile
4.  StatsStrip                   (existing)
5.  DataQualityBanner            (existing)
6.  ChartSection / TradingChart  (existing — DO NOT TOUCH)
7.  PriceExplainer               (existing)
8.  ValuationPanel               ← NEW: inserted after PriceExplainer
9.  FilingsTimeline              (existing)
10. NewsPanel                    ← NEW: inserted after FilingsTimeline
11. GatedContent                 (existing — SnapshotCard, PredictionChart, TechnicalsCard)
```

Each new section is rendered conditionally so pages with no data degrade gracefully — no skeleton loaders, no broken UI.

---

## 4. Data Sources

### 4.1 Hybrid Strategy

The system uses a **hybrid approach**: compute what is possible from existing Firestore data immediately, scaffold the `fundamentals/{ticker}` collection for richer future enrichment, and merge announcement feeds from existing `FinancialsDoc.announcements` with a new `news/{ticker}` scraper collection.

| Metric | Source | Available Now |
|--------|--------|---------------|
| Current price, change | `CompanyDoc` | ✓ |
| Day open / high / low | `TechnicalsDoc` (daily_return + price) | Derived |
| Volume, avg volume 30d | `TechnicalsDoc` | ✓ |
| 52W high / low | Computed from `CompanyDoc.price_history` (last 365d) | ✓ |
| Market cap | `current_price × companies.json[shares_outstanding]` | After companies.json update |
| P/E ratio | `current_price / FinancialsDoc.annual[0].eps` | ✓ (when EPS exists) |
| P/Book ratio | `current_price / FinancialsDoc.annual[0].bvps` | ✓ (when BVPS exists) |
| EPS (TTM) | `FinancialsDoc.annual[0].eps` | ✓ |
| Dividend yield | `FinancialsDoc.dividends[0].amount_kes / current_price × 100` | ✓ |
| Next dividend | `FinancialsDoc.dividends[0]` when `payment_date >= today`, else omitted chip | ✓ |
| ROE | `net_income_kes_mn / (bvps × shares_outstanding)` | Derived |
| Enterprise value | `fundamentals/{ticker}.enterprise_value_kes_bn` | Future (shows "—") |
| FY forward estimates | `fundamentals/{ticker}.estimates[]` | Future (shows "—") |
| ML consensus | `SnapshotDoc.model_breakdown` | ✓ |
| News / announcements | `FinancialsDoc.announcements` + `news/{ticker}/items` | Partial now, richer after scraper |
| Company profile fields | `companies.json` + new fields added | After companies.json update |

### 4.2 Firestore Collections (new)

**`fundamentals/{ticker}`** — initially empty per company, populated by future pipeline run:
```
{
  ticker: string,
  updated_at: Timestamp,
  shares_outstanding_mn: number | null,
  enterprise_value_kes_bn: number | null,
  employees: number | null,
  estimates: [{
    period: string,           // "FY2025E"
    eps_kes: number | null,
    revenue_kes_mn: number | null,
    net_income_kes_mn: number | null,
    pe_forward: number | null,
    source: string            // "consensus" | "management"
  }]
}
```

**`news/{ticker}/items/{id}`** — populated by `scrape_news.py`:
```
{
  date: string,               // ISO date "2026-07-24"
  title: string,
  category: "earnings" | "dividend" | "regulatory" | "agm" | "corporate_action" | "general",
  body: string | null,        // full text when available
  url: string | null,         // NSE PDF link or external URL
  source: "NSE" | "scraper",
  created_at: Timestamp
}
```

---

## 5. TypeScript Types (new additions to `index.ts`)

```typescript
export interface FundamentalsDoc {
  ticker: string;
  updated_at: string;
  shares_outstanding_mn: number | null;
  enterprise_value_kes_bn: number | null;
  employees: number | null;
  estimates: FundamentalsEstimate[];
}

export interface FundamentalsEstimate {
  period: string;
  eps_kes: number | null;
  revenue_kes_mn: number | null;
  net_income_kes_mn: number | null;
  pe_forward: number | null;
  source: "consensus" | "management";
}

export interface NewsItem {
  id: string;
  date: string;
  title: string;
  category: "earnings" | "dividend" | "regulatory" | "agm" | "corporate_action" | "general";
  body: string | null;
  url: string | null;
  source: "NSE" | "scraper";   // "NSE" = existing FinancialsDoc.announcements, "scraper" = pipeline
}
```

---

## 6. companies.json Additions

Each of the 61 entries gains optional fields (null when unknown):

```json
{
  "ticker": "COOP.NR",
  "shares_outstanding_mn": 5867,
  "website": "co-opbank.co.ke",
  "listing_year": 2008,
  "founded_year": 1965,
  "employees": 5600,
  "ceo": "Dr. Gideon Muriuki",
  "headquarters": "Nairobi, Kenya"
}
```

Fields are populated where verifiable from public NSE filings and company annual reports. Fields that cannot be verified are set to `null` and the UI renders "—" in their place. No placeholder or estimated values are added to `companies.json`.

---

## 7. Panel Designs

### 7.1 CompanyProfileCard

**Position:** Immediately after the trading terminal header.  
**Data:** `CompanyDoc` (existing) + new `companies.json` fields.  
**Interaction:** Description truncated to 3 lines; "Show more" toggle expands inline (same `useState(open)` accordion pattern as PriceExplainer).

**Visual layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│  [Logo]  Co-operative Bank of Kenya · COOP · NSE · Kenya 🇰🇪    │
│          Banking · Founded 1965 · Listed 2008                   │
│          CEO: Dr. Gideon Muriuki · 5,600 employees             │
│          co-opbank.co.ke ↗                                      │
│                                                                  │
│  Co-operative Bank of Kenya is jointly owned by Kenya's vast    │
│  cooperative movement and retail shareholders, making it one... │
│  [Show more ▼]                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Render conditions:** Always rendered. Fields with null values are omitted from the layout — no "—" placeholders shown in the profile block.

---

### 7.2 QuoteSummaryPanel

**Position:** After CompanyProfileCard, before StatsStrip.  
**Data:** `CompanyDoc`, `TechnicalsDoc`, `FinancialsDoc`, `SnapshotDoc`, `companies.json` (shares_outstanding).  
**Interaction:** Market Cap chip expands inline to show shares outstanding and computation method. ML consensus "View full breakdown" scrolls to the existing SnapshotCard via anchor link.

**Visual layout:**
```
┌─ QUOTE SUMMARY ──────────────────────────────────────────────────────────────┐
│                                                                               │
│  DAY RANGE                    52-WEEK RANGE                                   │
│  KES 13.15 ──────●─── 13.85  KES 10.80 ─────────────────●── KES 16.20      │
│                  ↑ current            ← 67% of 52W range →                  │
│                                                                               │
│  OPEN        VOLUME       AVG VOL 30D     MKT CAP [↕]     ENT. VALUE        │
│  KES 13.40   2.41M        1.83M           KES 42.3B        KES 39.1B         │
│                                                                               │
│  P/E         P/BOOK       EPS (TTM)       DIV YIELD        NEXT DIV          │
│  8.2×        1.07×        KES 1.63        4.1%             KES 0.55           │
│                                                                               │
│  ── ML MODEL CONSENSUS ──────────────────────────────────────────────────── │
│  ████████████░░░░░░   BUY 2 · HOLD 1 · SELL 0                               │
│  LSTM: BUY · XGBoost: BUY · ARIMA: HOLD                                     │
│  Model target: KES 14.80  ·  +10.4% upside  [View full breakdown →]         │
└───────────────────────────────────────────────────────────────────────────────┘
```

**52W range slider:** A CSS-only range track. The current price position is computed as `(current_price - low_52w) / (high_52w - low_52w) × 100` and applied as `left: {pct}%` on the indicator dot.

**ML consensus bar:** Filled width = `(buyCount / totalModels) × 100`. Color: emerald for majority buy, amber for majority hold, red for majority sell. Text labels use existing `model_breakdown` from `SnapshotDoc`.

**Day range derivation:** `TechnicalsDoc` does not store today's open/high/low. The day range row is **omitted entirely** unless intraday data is available via `CompanyDoc.intraday_today` (min/max of that series). Computing high/low from `daily_return` is backward-looking (yesterday's return) and misleading as a "day range" — do not use it for this purpose.

**Enterprise value:** Reads from `fundamentals/{ticker}.enterprise_value_kes_bn`; shows "—" when null.

**Market cap null handling:** Shows "—" until `companies.json` is updated with `shares_outstanding_mn`. This is not a blocker — the QuoteSummaryPanel renders without it; the market cap chip is simply absent.

**Render conditions:** Renders if `company.current_price !== null`. Individual metric chips whose source data is null are omitted from the grid (grid reflows via `flex-wrap`; no fixed-column layout that would leave gaps).

---

### 7.3 ValuationPanel

**Position:** After PriceExplainer, before FilingsTimeline.  
**Data:** `FinancialsDoc`, `CompanyDoc`, `FundamentalsDoc`, `companies.json` shares_outstanding.  
**Interaction:** Three tab buttons (Valuation / Income / Dividends) switch the table content. Panel header row collapses/expands the entire panel on click — same accordion as PriceExplainer. Sector median P/E is a hardcoded lookup map per sector (no external data).

**Visual layout — Valuation tab (default):**
```
┌─ COMPANY VALUATION ──────────────────────── [Valuation] [Income] [Dividends] ┐
│                                                                               │
│  ┌──────────────────────┬────────────┬────────────┬─────────────────────┐   │
│  │ Metric               │  FY 2023   │  FY 2024   │  FY 2025E           │   │
│  ├──────────────────────┼────────────┼────────────┼─────────────────────┤   │
│  │ Market Cap (KES B)   │  38.4      │  42.3      │  —                  │   │
│  │ P/E Ratio            │  9.5×      │  8.2×      │  7.5× (est.)        │   │
│  │ P/Book               │  1.10×     │  1.07×     │  —                  │   │
│  │ EPS (KES)            │  1.41      │  1.63      │  1.78 (est.)        │   │
│  │ BVPS (KES)           │  12.20     │  12.85     │  —                  │   │
│  │ Dividend Yield       │  3.7%      │  4.1%      │  —                  │   │
│  │ ROE                  │  11.3%     │  12.8%     │  —                  │   │
│  └──────────────────────┴────────────┴────────────┴─────────────────────┘   │
│                                                                               │
│  ── SECTOR PEER SNAPSHOT ──────────────────────────────────────────────────  │
│  Banking sector median P/E: 7.8×   This stock: 8.2×  (+5% vs sector)       │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Income tab:** Revenue (Net Banking Income / Net Revenue), Net Income, EPS across available annual periods. Shows bar sparkline (CSS width bars) for trend.

**Dividends tab:** Table of `FinancialsDoc.dividends` — amount, yield at payment date, ex-date, payment date, type. Most recent row highlighted.

**FY2025E column:** Reads from `FundamentalsDoc.estimates`. Shows "—" when `fundamentals/{ticker}` doc is empty or field is null. No interpolation or guessing.

**Sector medians lookup map** (hardcoded, no external call). If a company's `sector` field is absent from the map, the sector peer row is omitted — no "N/A" placeholder, no error:
```typescript
const SECTOR_MEDIAN_PE: Record<string, number> = {
  Banking: 7.8,
  Insurance: 6.2,
  "Manufacturing and Allied": 11.4,
  "Telecommunication and Technology": 18.5,
  "Energy and Petroleum": 9.1,
  "Commercial and Services": 13.2,
  Agricultural: 14.1,
  Investment: 8.9,
  "Real Estate Investment Trust": 22.0,
  "Automobiles and Accessories": 10.5,
  "Construction and Allied": 9.8,
  "Exchange Traded Funds": null,    // ETFs have no meaningful P/E; row omitted
};
```

**Multi-year data source mapping:**
- `EPS` → `FinancialResult.eps` per year row
- `BVPS` → `FinancialResult.bvps` per year row
- `Revenue` → `FinancialResult.revenue_kes_mn`
- `Net Income` → `FinancialResult.net_income_kes_mn`
- `ROE` (per year) → `net_income_kes_mn / (bvps × shares_outstanding_mn × 1_000_000) × 100`. If either `bvps` or `shares_outstanding_mn` is null, ROE cell shows "—".
- `Market Cap` (per year) → `closing_price_at_year_end` is not stored; use the P/E inverse: `eps × computed_pe` — too imprecise. Market cap column is omitted from the historical table; it appears only in the chip strip for the current price.
- `FY2025E` column → `FundamentalsDoc.estimates[]` matched by `period === "FY2025E"`. If `estimates` array is empty or no matching period, entire column is omitted rather than showing a "—" column.

**Render conditions:** Renders if `FinancialsDoc` exists and `FinancialsDoc.annual.length > 0` (using the `annual` field per the `FinancialsDoc` interface in `index.ts`). Falls back to a "No financials data yet" message otherwise.

---

### 7.4 NewsPanel

**Position:** After FilingsTimeline, before GatedContent.  
**Data:** `FinancialsDoc.announcements` (existing) merged with `news/{ticker}/items` (new Firestore subcollection).  
**Interaction:**
- Category filter tabs (All / Earnings / Dividends / Regulatory / Corporate Actions) filter the list client-side.
- Items with a `url` show an `↗ View filing` link that opens in a new tab with `rel="noopener noreferrer"`.
- Items without a `url` show `[Read more ▼]` that expands a `body` text block inline — same `useState(openId)` accordion pattern as PriceExplainer.
- "Load more" button increases the visible count by 5 (client-side pagination, no second Firestore call).

**Visual layout:**
```
┌─ LATEST NEWS & PRESS RELEASES ────────────────────────────────────────────── ┐
│                                                                               │
│  [All]  [Earnings]  [Dividends]  [Regulatory]  [Corporate Actions]           │
│                                                                               │
│  ● 3 days ago                                         [NSE] [EARNINGS]       │
│  24 Jul 2026 — H1 2026 Interim Results                                       │
│  Profit after tax KES 8.2B · NPL ratio improved to 6.2%                     │
│  ↗ View NSE filing                     [Read more ▼]                         │
│  ──────────────────────────────────────────────────────────────────────────  │
│  ● 39 days ago                                        [NSE] [DIVIDEND]       │
│  15 Jun 2026 — Final dividend KES 0.55 per share declared                    │
│  Record date: 30 Jun 2026 · Payment: 25 Jul 2026                             │
│  ↗ View NSE filing                                                            │
│  ──────────────────────────────────────────────────────────────────────────  │
│  ● 113 days ago                                    [NSE] [REGULATORY]        │
│  02 Apr 2026 — CBK grants approval for digital credit product rollout        │
│  [Read more ▼]                                                                │
│                                                                               │
│  Showing 3 of 12   ·   Load more ↓                                           │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Merging logic:** Convert `FinancialsDoc.announcements` (type `NSEAnnouncement`) to `NewsItem` format at render time. Merge with Firestore `news/{ticker}/items`. Sort descending by `date`, then descending by `source` ("scraper" > "NSE") as a stable tiebreaker so merges are deterministic. Deduplicate by `(date + title.slice(0, 80).toLowerCase())` composite key — if two items share the same key, the one with `source === "scraper"` is kept (richer body text); otherwise the first encountered is kept. This avoids over-deduplication of legitimately different announcements with similar prefixes.

**Firestore fetch cap:** `fetchNews()` queries `news/{ticker}/items` with `orderBy("date", "desc").limit(50)`. Combined with up to ~20 `FinancialsDoc.announcements`, the merged list is bounded at ~70 items. Client-side pagination shows 5 items initially, increasing by 5 per "Load more" click. This avoids unbounded renders on companies with large announcement histories.

**Category chip colours:**
- `[EARNINGS]` — emerald
- `[DIVIDEND]` — sky blue
- `[REGULATORY]` — amber
- `[AGM]` — violet
- `[CORPORATE ACTION]` — orange
- `[GENERAL]` — slate

**Source chip:**
- `[NSE]` — slate-600 border, existing announcements
- `[SCRAPER]` — indigo border, items from new pipeline

**Time-relative labels:** `"3 days ago"` computed from `new Date()` vs `item.date`. Shown alongside the absolute date.

**Render conditions:** Always rendered if company has any announcements or news items. If none: shows "No announcements on record for this company." — no panel hidden.

---

## 8. Python News Scraper (`pipeline/scripts/scrape_news.py`)

### Purpose
Fetches NSE corporate announcements for all 61 companies and pushes structured `NewsItem` documents to Firestore `news/{ticker}/items`.

### Sources (in priority order)
1. **NSE Corporate Announcements page** — `https://www.nse.co.ke/market-statistics/corporate-announcements/` — parse HTML table for announcements per ticker
2. **Existing `FinancialsDoc.announcements`** — already in Firestore; scraper does not duplicate these, only adds net-new items

### Design invariants
- Idempotent: uses announcement title + date as the document ID (slugified). Re-running never creates duplicates.
- Fails gracefully per ticker: one company's fetch failure does not stop others.
- Writes only to `news/{ticker}/items`, never touches `FinancialsDoc`.
- Exits 0 always — scraper is best-effort supplementary data.

### CI integration
Added to `daily_inference.yml` as a new step after inference, before the existing push-to-Firestore step:

```yaml
- name: Scrape NSE news
  run: |
    set -euo pipefail
    cd pipeline
    python scripts/scrape_news.py
  continue-on-error: true   # non-blocking — enrichment, not core data
```

---

## 9. Firestore Helpers (new additions)

**`firestore.ts` additions:**
```typescript
export async function fetchFundamentals(ticker: string): Promise<FundamentalsDoc | null>
export async function fetchNews(ticker: string): Promise<NewsItem[]>
```

**`useCompany.ts` additions:**
```typescript
export function useFundamentals(ticker: string)  // wraps fetchFundamentals
export function useNews(ticker: string)           // wraps fetchNews, returns []  on miss
```

Both use TanStack Query with `staleTime: 5 * 60 * 1000` (5 min). `useNews` returns `[]` if the subcollection is empty — never throws.

---

## 10. Firestore Security Rules

The new collections require read access for authenticated users (matching existing rules for other collections). No new write rules on the client — all writes go through the pipeline service account.

```
match /fundamentals/{ticker} {
  allow read: if request.auth != null;
}
match /news/{ticker}/items/{itemId} {
  allow read: if request.auth != null;
}
```

---

## 11. Testing

### Unit tests (Vitest, co-located)
- `QuoteSummaryPanel.test.tsx` — 52W slider position computation, null price handling, ML consensus bar fill percentage
- `ValuationPanel.test.tsx` — tab switching, sector median lookup, "—" rendering for null fields
- `NewsPanel.test.tsx` — category filter, deduplication logic, time-relative label computation, load-more pagination
- `CompanyProfileCard.test.tsx` — description truncation, show-more toggle

### Python tests (pytest)
- `tests/pipeline/test_scrape_news.py` — mock HTTP responses, idempotency check (same item written twice = one Firestore doc), per-ticker failure isolation

### Manual verification checklist
- [ ] All 4 panels render without error for a company with full data (COOP, KCB)
- [ ] All 4 panels render without error for a company with minimal data (EGAD, HAFR)
- [ ] 52W slider clamps correctly when current price = 52W low or high
- [ ] ValuationPanel "—" shown for null fields, not "0" or "NaN"
- [ ] NewsPanel external links open new tab with `rel="noopener noreferrer"`
- [ ] NewsPanel inline expand shows body text when no URL present
- [ ] CompanyProfileCard shows only populated fields, no blank rows
- [ ] Existing TradingChart and PredictionChart scroll and render unaffected

---

## 12. Out of Scope

- Real-time price streaming (existing polling strategy is unchanged)
- Analyst recommendations from external data providers (our ML models serve this role)
- MarketScreener data scraping (blocked; used only for design reference)
- ESG ratings
- Options / derivatives data
- Portfolio tracking features
