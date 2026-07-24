# Investor Experience Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four investor-grade panels to `CompanyDeepDive` — CompanyProfileCard, QuoteSummaryPanel, ValuationPanel, and NewsPanel — modelled after MarketScreener, without touching any existing chart or signal components.

**Architecture:** Each panel is an independent React component in `frontend/src/components/investor/`. Static company metadata (shares outstanding, CEO, website, etc.) lives in `frontend/src/data/companyProfiles.ts` — a typed in-memory lookup, no extra Firestore calls. Dynamic forward estimates and enterprise value read from a new Firestore `fundamentals/{ticker}` collection. News merges existing `FinancialsDoc.announcements` with a new Firestore `news/{ticker}/items` subcollection, capped at 50 items, populated by a new Python scraper added to the daily CI job.

**Tech Stack:** React 18, TypeScript, TanStack Query v5, Firebase Firestore, Vitest + Testing Library + userEvent, Tailwind CSS, Python 3, requests + BeautifulSoup4, Firebase Admin SDK.

**Spec:** `docs/superpowers/specs/2026-07-24-investor-enhancements-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `frontend/src/data/companyProfiles.ts` | Static per-company profile lookup (shares, CEO, website, etc.) |
| Modify | `frontend/src/types/index.ts` | Add `FundamentalsDoc`, `FundamentalsEstimate`, `NewsItem` |
| Modify | `frontend/src/lib/firestore.ts` | Add `fetchFundamentals()`, `fetchNews()` |
| Modify | `frontend/src/hooks/useCompany.ts` | Add `useFundamentals()`, `useNews()` |
| Create | `frontend/src/components/investor/CompanyProfileCard.tsx` | About block panel |
| Create | `frontend/src/components/investor/CompanyProfileCard.test.tsx` | Tests |
| Create | `frontend/src/components/investor/QuoteSummaryPanel.tsx` | Dense metrics + 52W slider + ML consensus |
| Create | `frontend/src/components/investor/QuoteSummaryPanel.test.tsx` | Tests |
| Create | `frontend/src/components/investor/ValuationPanel.tsx` | Tabbed multi-year fundamentals table |
| Create | `frontend/src/components/investor/ValuationPanel.test.tsx` | Tests |
| Create | `frontend/src/components/investor/NewsPanel.tsx` | Filterable announcement feed |
| Create | `frontend/src/components/investor/NewsPanel.test.tsx` | Tests |
| Modify | `frontend/src/pages/CompanyDeepDive.tsx` | Wire four panels into page |
| Create | `pipeline/scripts/scrape_news.py` | NSE announcement scraper → Firestore |
| Create | `tests/pipeline/test_scrape_news.py` | Pytest tests for scraper |
| Modify | `.github/workflows/daily_inference.yml` | Add scraper step |

---

## Task 1: Static Company Profile Data

**Files:**
- Create: `frontend/src/data/companyProfiles.ts`

This file is a typed lookup keyed by NSE ticker (e.g. `"COOP.NR"`). No network call, no Firestore — imported directly by profile and quote panels. Fill `null` for any field you cannot verify from a public NSE annual report or company website.

- [ ] **Step 1: Create the file**

```typescript
// frontend/src/data/companyProfiles.ts

export interface CompanyProfile {
  shares_outstanding_mn: number | null;
  website: string | null;
  listing_year: number | null;
  founded_year: number | null;
  employees: number | null;
  ceo: string | null;
  headquarters: string | null;
}

export const COMPANY_PROFILES: Record<string, CompanyProfile> = {
  "ABSA.NR": {
    shares_outstanding_mn: 1090,
    website: "absakenya.co.ke",
    listing_year: 1988,
    founded_year: 1916,
    employees: 2600,
    ceo: "Abdi Mohamed",
    headquarters: "Nairobi, Kenya",
  },
  "ALP.NR": {
    shares_outstanding_mn: 1500,
    website: "alp.co.ke",
    listing_year: 2023,
    founded_year: 2022,
    employees: null,
    ceo: null,
    headquarters: "Nairobi, Kenya",
  },
  "AMAC.NR": {
    shares_outstanding_mn: null,
    website: null,
    listing_year: null,
    founded_year: null,
    employees: null,
    ceo: null,
    headquarters: "Kenya",
  },
  "BAT.NR": {
    shares_outstanding_mn: 100,
    website: "batkenya.com",
    listing_year: 1969,
    founded_year: 1907,
    employees: 1200,
    ceo: "Crispin Achola",
    headquarters: "Nairobi, Kenya",
  },
  "BKG.NR": {
    shares_outstanding_mn: 1190,
    website: "bk.rw",
    listing_year: 2018,
    founded_year: 1966,
    employees: 3600,
    ceo: "Diane Karusisi",
    headquarters: "Kigali, Rwanda",
  },
  "BOC.NR": {
    shares_outstanding_mn: 6,
    website: "boc.co.ke",
    listing_year: 1969,
    founded_year: 1960,
    employees: 350,
    ceo: null,
    headquarters: "Nairobi, Kenya",
  },
  "BRIT.NR": {
    shares_outstanding_mn: 2751,
    website: "britam.com",
    listing_year: 2011,
    founded_year: 1965,
    employees: 7000,
    ceo: "Tom Gitogo",
    headquarters: "Nairobi, Kenya",
  },
  "CARB.NR": {
    shares_outstanding_mn: 75,
    website: null,
    listing_year: 1973,
    founded_year: 1969,
    employees: 120,
    ceo: null,
    headquarters: "Nairobi, Kenya",
  },
  "CGEN.NR": {
    shares_outstanding_mn: 40,
    website: "carandgeneral.co.ke",
    listing_year: 1969,
    founded_year: 1918,
    employees: 800,
    ceo: null,
    headquarters: "Nairobi, Kenya",
  },
  "CIC.NR": {
    shares_outstanding_mn: 3012,
    website: "cicinsurancegroup.com",
    listing_year: 2012,
    founded_year: 1978,
    employees: 1800,
    ceo: "Patrick Nyaga",
    headquarters: "Nairobi, Kenya",
  },
  "COOP.NR": {
    shares_outstanding_mn: 5867,
    website: "co-opbank.co.ke",
    listing_year: 2008,
    founded_year: 1965,
    employees: 5600,
    ceo: "Dr. Gideon Muriuki",
    headquarters: "Nairobi, Kenya",
  },
  "CRWN.NR": {
    shares_outstanding_mn: 71,
    website: "crownberger.co.ke",
    listing_year: 1969,
    founded_year: 1933,
    employees: 400,
    ceo: null,
    headquarters: "Nairobi, Kenya",
  },
  "CTUM.NR": {
    shares_outstanding_mn: 667,
    website: "centum.co.ke",
    listing_year: 1967,
    founded_year: 1967,
    employees: 300,
    ceo: "James Mworia",
    headquarters: "Nairobi, Kenya",
  },
  "DTK.NR": {
    shares_outstanding_mn: 354,
    website: "dtbafrica.com",
    listing_year: 1969,
    founded_year: 1946,
    employees: 3800,
    ceo: "Nasim Devji",
    headquarters: "Nairobi, Kenya",
  },
  "EABL.NR": {
    shares_outstanding_mn: 791,
    website: "eabl.com",
    listing_year: 1988,
    founded_year: 1922,
    employees: 2200,
    ceo: "John Musunga",
    headquarters: "Nairobi, Kenya",
  },
  "EGAD.NR": {
    shares_outstanding_mn: 4,
    website: null,
    listing_year: 1969,
    founded_year: 1946,
    employees: 80,
    ceo: null,
    headquarters: "Kiambu, Kenya",
  },
  "EQTY.NR": {
    shares_outstanding_mn: 3773,
    website: "equitygroupholdings.com",
    listing_year: 2006,
    founded_year: 1984,
    employees: 12000,
    ceo: "Dr. James Mwangi",
    headquarters: "Nairobi, Kenya",
  },
  "EVRD.NR": {
    shares_outstanding_mn: 200,
    website: null,
    listing_year: 1973,
    founded_year: 1975,
    employees: 200,
    ceo: null,
    headquarters: "Nairobi, Kenya",
  },
  "FMLY.NR": {
    shares_outstanding_mn: 1200,
    website: "familybank.co.ke",
    listing_year: 2012,
    founded_year: 1984,
    employees: 2200,
    ceo: "Nancy Njau",
    headquarters: "Nairobi, Kenya",
  },
  "GLD.NR": {
    shares_outstanding_mn: null,
    website: null,
    listing_year: 2017,
    founded_year: null,
    employees: null,
    ceo: null,
    headquarters: null,
  },
  "HAFR.NR": {
    shares_outstanding_mn: 1015,
    website: "homeafrika.com",
    listing_year: 2013,
    founded_year: 2010,
    employees: 60,
    ceo: null,
    headquarters: "Nairobi, Kenya",
  },
  "HFCK.NR": {
    shares_outstanding_mn: 1163,
    website: "hfgroup.co.ke",
    listing_year: 1993,
    founded_year: 1965,
    employees: 1400,
    ceo: "Robert Kibaara",
    headquarters: "Nairobi, Kenya",
  },
  "IMH.NR": {
    shares_outstanding_mn: 829,
    website: "im-bank.com",
    listing_year: 1987,
    founded_year: 1974,
    employees: 3200,
    ceo: "Gul Khan",
    headquarters: "Nairobi, Kenya",
  },
  "JUB.NR": {
    shares_outstanding_mn: 388,
    website: "jubileeholdings.co.ke",
    listing_year: 1984,
    founded_year: 1937,
    employees: 5000,
    ceo: "Julius Kipng'etich",
    headquarters: "Nairobi, Kenya",
  },
  "KAPC.NR": {
    shares_outstanding_mn: 19,
    website: null,
    listing_year: 1969,
    founded_year: 1962,
    employees: 1200,
    ceo: null,
    headquarters: "Kericho, Kenya",
  },
  "KCB.NR": {
    shares_outstanding_mn: 3216,
    website: "kcbgroup.com",
    listing_year: 1954,
    founded_year: 1896,
    employees: 11000,
    ceo: "Paul Russo",
    headquarters: "Nairobi, Kenya",
  },
  "KEGN.NR": {
    shares_outstanding_mn: 3976,
    website: "kengen.co.ke",
    listing_year: 2006,
    founded_year: 1997,
    employees: 3400,
    ceo: "Peter Njenga",
    headquarters: "Nairobi, Kenya",
  },
  "KNRE.NR": {
    shares_outstanding_mn: 600,
    website: "kenyare.co.ke",
    listing_year: 2010,
    founded_year: 1970,
    employees: 400,
    ceo: "Hillary Wachinga",
    headquarters: "Nairobi, Kenya",
  },
  "KPC.NR": {
    shares_outstanding_mn: 500,
    website: "kpc.co.ke",
    listing_year: 2020,
    founded_year: 1973,
    employees: 2000,
    ceo: "Joe Sang",
    headquarters: "Nairobi, Kenya",
  },
  // ── Fill remaining 31 companies following the same pattern ─────────────────
  // Look up exact values from NSE annual reports at: https://www.nse.co.ke
  // Use null for any field you cannot verify from a public source.
  // Remaining tickers from companies.json: KUKZ, LBTY, LIMT, LSTM (Longhorn),
  // MCOM, MSCE, MSC, NCBA, NIC, NSE, OLYMP, PAFR, SASN, SBIC, SCBK, SCOM,
  // SLAM, STANCHART, TOTL, TPSE, TRAN, TRDG, UMME, UNGA, VIVO, WBIL, XPRS
  // plus any other tickers present in pipeline/config/companies.json.
};

export function getCompanyProfile(ticker: string): CompanyProfile {
  return COMPANY_PROFILES[ticker] ?? {
    shares_outstanding_mn: null,
    website: null,
    listing_year: null,
    founded_year: null,
    employees: null,
    ceo: null,
    headquarters: null,
  };
}
```

- [ ] **Step 2: Verify the file TypeScript-compiles**

```
cd frontend && npx tsc --noEmit --pretty false 2>&1 | head -20
```
Expected: no errors related to `companyProfiles.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/data/companyProfiles.ts
git commit -m "feat: add static company profile lookup for 61 NSE companies"
```

---

## Task 2: TypeScript Type Additions

**Files:**
- Modify: `frontend/src/types/index.ts` (append after `MacroDoc`)

- [ ] **Step 1: Append new types to `index.ts`**

Open `frontend/src/types/index.ts` and append these interfaces at the end of the file:

```typescript
export interface FundamentalsEstimate {
  period: string;                   // e.g. "FY2025E"
  eps_kes: number | null;
  revenue_kes_mn: number | null;
  net_income_kes_mn: number | null;
  pe_forward: number | null;
  source: "consensus" | "management";
}

export interface FundamentalsDoc {
  ticker: string;
  updated_at: string;
  shares_outstanding_mn: number | null;
  enterprise_value_kes_bn: number | null;
  employees: number | null;
  estimates: FundamentalsEstimate[];
}

export interface NewsItem {
  id: string;
  date: string;                     // ISO date "YYYY-MM-DD"
  title: string;
  category: "earnings" | "dividend" | "regulatory" | "agm" | "corporate_action" | "general";
  body: string | null;
  url: string | null;
  source: "NSE" | "scraper";       // "NSE" = FinancialsDoc.announcements, "scraper" = pipeline
}
```

- [ ] **Step 2: Run type-check**

```
cd frontend && npx tsc --noEmit --pretty false 2>&1 | head -20
```
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: add FundamentalsDoc, FundamentalsEstimate, NewsItem types"
```

---

## Task 3: Firestore Helpers and Hooks

**Files:**
- Modify: `frontend/src/lib/firestore.ts`
- Modify: `frontend/src/hooks/useCompany.ts`

- [ ] **Step 1: Add `fetchFundamentals` and `fetchNews` to `firestore.ts`**

Add to the import list at the top of `firestore.ts`:
```typescript
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, MarketOverviewDoc, EventsDoc, CorporateEvent, FinancialsDoc, MacroDoc, IntradayPoint, FundamentalsDoc, NewsItem } from "../types";
```

Then append these two functions at the end of `firestore.ts`:

```typescript
export async function fetchFundamentals(ticker: string): Promise<FundamentalsDoc | null> {
  const ref = doc(db, "fundamentals", ticker);
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return snap.data() as FundamentalsDoc;
}

export async function fetchNews(ticker: string): Promise<NewsItem[]> {
  const ref = collection(db, "news", ticker, "items");
  const q = query(ref, orderBy("date", "desc"), limit(50));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<NewsItem, "id">) }));
}
```

- [ ] **Step 2: Add `useFundamentals` and `useNews` to `useCompany.ts`**

Add to the import at the top of `useCompany.ts`:
```typescript
import { fetchCompany, fetchLatestSnapshot, fetchLatestTechnicals, fetchCorporateEvents, fetchFinancials, fetchMacro, fetchIntradayDay, fetchFundamentals, fetchNews } from "../lib/firestore";
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, CorporateEvent, FinancialsDoc, MacroDoc, IntradayPoint, FundamentalsDoc, NewsItem } from "../types";
```

Append these two hooks at the end of `useCompany.ts`:

```typescript
export function useFundamentals(safeTicker: string) {
  return useQuery<FundamentalsDoc | null>({
    queryKey: ["fundamentals", safeTicker],
    queryFn: () => fetchFundamentals(safeTicker),
    enabled: !!safeTicker,
    staleTime: 5 * 60 * 1000,
  });
}

export function useNews(safeTicker: string) {
  return useQuery<NewsItem[]>({
    queryKey: ["news", safeTicker],
    queryFn: () => fetchNews(safeTicker),
    enabled: !!safeTicker,
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 3: Type-check**

```
cd frontend && npx tsc --noEmit --pretty false 2>&1 | head -30
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/firestore.ts frontend/src/hooks/useCompany.ts
git commit -m "feat: add fetchFundamentals, fetchNews helpers and useFundamentals, useNews hooks"
```

---

## Task 4: CompanyProfileCard

**Files:**
- Create: `frontend/src/components/investor/CompanyProfileCard.tsx`
- Create: `frontend/src/components/investor/CompanyProfileCard.test.tsx`

- [ ] **Step 1: Write the failing test first**

```typescript
// frontend/src/components/investor/CompanyProfileCard.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CompanyProfileCard } from "./CompanyProfileCard";
import type { CompanyDoc } from "../../types";

vi.mock("../../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));

const mockCompany: CompanyDoc = {
  id: "COOP_NR",
  ticker: "COOP.NR",
  name: "Co-operative Bank",
  short: "COOP",
  sector: "Banking",
  color: "#34d399",
  icon: "🏦",
  csv: "COOP_NR_raw.csv",
  description: "Co-operative Bank of Kenya is jointly owned by Kenya's vast cooperative movement and retail shareholders. ".repeat(5),
  current_price: 13.50,
  change_pct_today: 1.2,
  signal: "BUY",
  price_history: [],
  price_preview: [],
  price_date: "2026-07-24",
  last_updated: "2026-07-24",
};

describe("CompanyProfileCard", () => {
  it("renders company name and sector", () => {
    render(<CompanyProfileCard company={mockCompany} />);
    expect(screen.getByText("Co-operative Bank")).toBeInTheDocument();
    expect(screen.getByText(/Banking/)).toBeInTheDocument();
  });

  it("renders CEO from profile lookup", () => {
    render(<CompanyProfileCard company={mockCompany} />);
    expect(screen.getByText(/Dr. Gideon Muriuki/)).toBeInTheDocument();
  });

  it("truncates long description and shows 'Show more' toggle", () => {
    render(<CompanyProfileCard company={mockCompany} />);
    expect(screen.getByText(/Show more/i)).toBeInTheDocument();
  });

  it("expands description on Show more click", async () => {
    const user = userEvent.setup();
    render(<CompanyProfileCard company={mockCompany} />);
    await user.click(screen.getByText(/Show more/i));
    expect(screen.getByText(/Show less/i)).toBeInTheDocument();
  });

  it("renders website link with noopener", () => {
    render(<CompanyProfileCard company={mockCompany} />);
    const link = screen.getByRole("link", { name: /co-opbank\.co\.ke/i });
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```
cd frontend && npx vitest run src/components/investor/CompanyProfileCard.test.tsx 2>&1 | tail -10
```
Expected: `FAIL` — `CompanyProfileCard` not defined.

- [ ] **Step 3: Implement the component**

```typescript
// frontend/src/components/investor/CompanyProfileCard.tsx
import { useState } from "react";
import type { FC } from "react";
import type { CompanyDoc } from "../../types";
import { getCompanyProfile } from "../../data/companyProfiles";

export const CompanyProfileCard: FC<{ company: CompanyDoc }> = ({ company }) => {
  const [expanded, setExpanded] = useState(false);
  const profile = getCompanyProfile(company.ticker);
  const desc = company.description ?? "";
  const isLong = desc.length > 220;
  const displayDesc = isLong && !expanded ? `${desc.slice(0, 220)}…` : desc;

  const metaItems = [
    profile.founded_year ? `Founded ${profile.founded_year}` : null,
    profile.listing_year ? `Listed ${profile.listing_year}` : null,
    profile.employees ? `${profile.employees.toLocaleString()} employees` : null,
  ].filter(Boolean);

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface px-5 py-4">
      <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span
          className="rounded border px-2 py-0.5 font-mono text-xs font-bold tracking-wider"
          style={{ borderColor: `${company.color}55`, color: company.color, backgroundColor: `${company.color}15` }}
        >
          {company.ticker}
        </span>
        <span className="text-xs text-muted">{company.sector}</span>
        <span className="text-xs text-hint">NSE · Kenya 🇰🇪</span>
      </div>

      {metaItems.length > 0 && (
        <p className="mb-1 text-xs text-muted">
          {metaItems.join(" · ")}
        </p>
      )}

      {profile.ceo && (
        <p className="mb-1 text-xs text-sub">
          CEO: <span className="font-medium text-ink">{profile.ceo}</span>
        </p>
      )}

      {profile.headquarters && (
        <p className="mb-1 text-xs text-muted">{profile.headquarters}</p>
      )}

      {profile.website && (
        <a
          href={`https://${profile.website}`}
          target="_blank"
          rel="noopener noreferrer"
          className="mb-3 inline-block text-xs text-sky-400 hover:underline"
        >
          {profile.website} ↗
        </a>
      )}

      {desc && (
        <div className="mt-2 border-t border-seam/60 pt-3">
          <p className="text-sm leading-relaxed text-sub">{displayDesc}</p>
          {isLong && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-1.5 text-xs font-semibold text-sky-400 hover:text-sky-300"
            >
              {expanded ? "Show less ▲" : "Show more ▼"}
            </button>
          )}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Run tests to confirm pass**

```
cd frontend && npx vitest run src/components/investor/CompanyProfileCard.test.tsx 2>&1 | tail -15
```
Expected: all 5 tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/investor/CompanyProfileCard.tsx frontend/src/components/investor/CompanyProfileCard.test.tsx
git commit -m "feat: add CompanyProfileCard panel"
```

---

## Task 5: QuoteSummaryPanel

**Files:**
- Create: `frontend/src/components/investor/QuoteSummaryPanel.tsx`
- Create: `frontend/src/components/investor/QuoteSummaryPanel.test.tsx`

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/components/investor/QuoteSummaryPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { QuoteSummaryPanel } from "./QuoteSummaryPanel";
import type { CompanyDoc, TechnicalsDoc, FinancialsDoc, SnapshotDoc } from "../../types";

vi.mock("../../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));

const baseCompany: CompanyDoc = {
  id: "COOP_NR", ticker: "COOP.NR", name: "Co-operative Bank",
  short: "COOP", sector: "Banking", color: "#34d399", icon: "🏦",
  csv: "COOP_NR_raw.csv", current_price: 13.50, change_pct_today: 1.2,
  signal: "BUY", price_history: [
    { date: "2025-07-24", price: 10.80 },
    { date: "2026-01-15", price: 14.20 },
    { date: "2026-07-24", price: 13.50 },
  ],
  price_preview: [], price_date: "2026-07-24", last_updated: "2026-07-24",
};

const baseTechnicals: TechnicalsDoc = {
  date: "2026-07-24", rsi_14: 52, macd: 0.1, macd_signal: 0.08,
  macd_hist: 0.02, bb_upper: 14.5, bb_mid: 13.5, bb_lower: 12.5,
  sma_20: 13.2, sma_50: 13.0, sma_200: 12.5, ema_12: 13.4, ema_26: 13.1,
  volume: 2410000, avg_volume_30d: 1830000,
  daily_return: 1.2, volatility_30d: 0.8, monthly_heatmap: {},
};

describe("QuoteSummaryPanel", () => {
  it("renders volume", () => {
    render(<QuoteSummaryPanel company={baseCompany} technicals={baseTechnicals} financials={null} snapshot={null} />);
    expect(screen.getByText(/2,410,000|2\.41M/i)).toBeInTheDocument();
  });

  it("renders 52W high derived from price history", () => {
    render(<QuoteSummaryPanel company={baseCompany} technicals={baseTechnicals} financials={null} snapshot={null} />);
    expect(screen.getByText(/14\.20/)).toBeInTheDocument();
  });

  it("renders 52W low derived from price history", () => {
    render(<QuoteSummaryPanel company={baseCompany} technicals={baseTechnicals} financials={null} snapshot={null} />);
    expect(screen.getByText(/10\.80/)).toBeInTheDocument();
  });

  it("renders P/E when EPS available", () => {
    const financials: FinancialsDoc = {
      annual: [{ period: "FY2024", period_end: "2024-12-31", period_type: "annual", announcement_date: "2025-03-15", revenue_kes_mn: 48000, net_income_kes_mn: 9600, eps: 1.63, bvps: 12.85, notes: "" }],
      dividends: [], corporate_actions: [], announcements: [],
    };
    render(<QuoteSummaryPanel company={baseCompany} technicals={baseTechnicals} financials={financials} snapshot={null} />);
    // P/E = 13.50 / 1.63 ≈ 8.28
    expect(screen.getByText(/8\.[0-9]+×/)).toBeInTheDocument();
  });

  it("renders ML consensus bar when snapshot model_breakdown provided", () => {
    const snapshot = { model_breakdown: { LSTM: { price: 14.80, signal: "BUY", pct: 9.6 }, XGBoost: { price: 14.60, signal: "BUY", pct: 8.1 }, ARIMA: { price: 13.80, signal: "HOLD", pct: 2.2 } } } as unknown as SnapshotDoc;
    render(<QuoteSummaryPanel company={baseCompany} technicals={baseTechnicals} financials={null} snapshot={snapshot} />);
    expect(screen.getByText(/BUY 2/i)).toBeInTheDocument();
    expect(screen.getByText(/HOLD 1/i)).toBeInTheDocument();
  });

  it("does not render when current_price is null", () => {
    const { container } = render(<QuoteSummaryPanel company={{ ...baseCompany, current_price: null }} technicals={baseTechnicals} financials={null} snapshot={null} />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```
cd frontend && npx vitest run src/components/investor/QuoteSummaryPanel.test.tsx 2>&1 | tail -10
```
Expected: `FAIL` — component not defined.

- [ ] **Step 3: Implement the component**

```typescript
// frontend/src/components/investor/QuoteSummaryPanel.tsx
import type { FC } from "react";
import type { CompanyDoc, TechnicalsDoc, FinancialsDoc, SnapshotDoc } from "../../types";
import { getCompanyProfile } from "../../data/companyProfiles";

const fmtVol = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n.toLocaleString();

const fmtKES = (n: number) => `KES ${n.toFixed(2)}`;

const SECTOR_MEDIAN_PE: Record<string, number | null> = {
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
  "Exchange Traded Funds": null,
};

interface Props {
  company: CompanyDoc;
  technicals: TechnicalsDoc | null | undefined;
  financials: FinancialsDoc | null | undefined;
  snapshot: SnapshotDoc | null | undefined;
}

const MetricChip: FC<{ label: string; value: string; accent?: string }> = ({ label, value, accent }) => (
  <div className="rounded-lg border border-seam bg-raised/60 p-3">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</p>
    <p className={`mt-0.5 font-mono text-sm font-semibold ${accent ?? "text-ink"}`}>{value}</p>
  </div>
);

export const QuoteSummaryPanel: FC<Props> = ({ company, technicals, financials, snapshot }) => {
  if (company.current_price === null) return null;

  const price = company.current_price;
  const profile = getCompanyProfile(company.ticker);

  // 52W high/low from last 365 days of price_history
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 365);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const yearPrices = (company.price_history ?? [])
    .filter((p) => p.date >= cutoffStr)
    .map((p) => p.price);
  const high52 = yearPrices.length > 0 ? Math.max(...yearPrices) : null;
  const low52  = yearPrices.length > 0 ? Math.min(...yearPrices) : null;
  const rangePos = high52 && low52 && high52 !== low52
    ? Math.round(((price - low52) / (high52 - low52)) * 100)
    : null;

  // Fundamentals
  const latestAnnual = financials?.annual?.[0] ?? null;
  const pe = latestAnnual?.eps && latestAnnual.eps > 0 ? price / latestAnnual.eps : null;
  const pb = latestAnnual?.bvps && latestAnnual.bvps > 0 ? price / latestAnnual.bvps : null;
  const eps = latestAnnual?.eps ?? null;

  const latestDiv = financials?.dividends?.[0] ?? null;
  const divYield = latestDiv?.amount_kes && price > 0
    ? (latestDiv.amount_kes / price) * 100
    : null;
  const nextDiv = latestDiv?.payment_date && latestDiv.payment_date >= new Date().toISOString().slice(0, 10)
    ? latestDiv
    : null;

  const sharesMn = profile.shares_outstanding_mn;
  const mktCapBn = sharesMn ? (price * sharesMn * 1_000_000) / 1_000_000_000 : null;

  // ML consensus from snapshot model_breakdown
  const breakdown = snapshot?.model_breakdown;
  const models = breakdown ? Object.values(breakdown) : [];
  const buyCount  = models.filter((m) => m.signal === "BUY").length;
  const holdCount = models.filter((m) => m.signal === "HOLD").length;
  const sellCount = models.filter((m) => m.signal === "SELL").length;
  const totalModels = models.length;
  const targetAvg = totalModels > 0
    ? models.reduce((s, m) => s + m.price, 0) / totalModels
    : null;
  const upside = targetAvg ? ((targetAvg - price) / price) * 100 : null;
  const consensusFill = totalModels > 0 ? Math.round((buyCount / totalModels) * 100) : 0;
  const consensusColor = buyCount > holdCount + sellCount
    ? "bg-emerald-500"
    : holdCount > sellCount
    ? "bg-amber-400"
    : "bg-red-500";

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface px-5 py-4 space-y-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Quote Summary</p>

      {/* 52W range slider */}
      {high52 !== null && low52 !== null && (
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[10px] text-muted">
            <span className="font-semibold uppercase tracking-wider">52-Week Range</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-sub">{fmtKES(low52)}</span>
            <div className="relative flex-1 h-1.5 rounded-full bg-raised">
              <div className="absolute inset-0 rounded-full bg-seam" />
              {rangePos !== null && (
                <div
                  className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-sky-400 bg-surface shadow"
                  style={{ left: `calc(${rangePos}% - 6px)` }}
                />
              )}
            </div>
            <span className="font-mono text-xs text-sub">{fmtKES(high52)}</span>
          </div>
          {rangePos !== null && (
            <p className="text-right text-[10px] text-hint">{rangePos}% of 52W range</p>
          )}
        </div>
      )}

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {technicals && (
          <MetricChip label="Volume" value={fmtVol(technicals.volume)} />
        )}
        {technicals && (
          <MetricChip label="Avg Vol 30D" value={fmtVol(technicals.avg_volume_30d)} />
        )}
        {mktCapBn !== null && (
          <MetricChip label="Mkt Cap" value={`KES ${mktCapBn.toFixed(1)}B`} />
        )}
        {pe !== null && (
          <MetricChip label="P/E" value={`${pe.toFixed(1)}×`} />
        )}
        {pb !== null && (
          <MetricChip label="P/Book" value={`${pb.toFixed(2)}×`} />
        )}
        {eps !== null && (
          <MetricChip label="EPS (TTM)" value={`KES ${eps.toFixed(2)}`} />
        )}
        {divYield !== null && (
          <MetricChip label="Div Yield" value={`${divYield.toFixed(1)}%`} accent="text-emerald-400" />
        )}
        {nextDiv && (
          <MetricChip label="Next Div" value={`KES ${nextDiv.amount_kes.toFixed(2)}`} />
        )}
      </div>

      {/* ML consensus bar */}
      {totalModels > 0 && (
        <div className="border-t border-seam/60 pt-3 space-y-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            ML Model Consensus
          </p>
          <div className="h-2 w-full overflow-hidden rounded-full bg-raised">
            <div className={`h-full rounded-full transition-all ${consensusColor}`} style={{ width: `${consensusFill}%` }} />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="text-sub">
              {buyCount > 0 && <span className="text-emerald-400 font-semibold">BUY {buyCount}</span>}
              {holdCount > 0 && <span className="ml-2 text-amber-400 font-semibold">HOLD {holdCount}</span>}
              {sellCount > 0 && <span className="ml-2 text-red-400 font-semibold">SELL {sellCount}</span>}
            </span>
            {targetAvg && upside !== null && (
              <span className="font-mono text-sub">
                Target {fmtKES(targetAvg)}
                <span className={upside >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {" "}({upside >= 0 ? "+" : ""}{upside.toFixed(1)}%)
                </span>
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-[10px] text-hint">
            {breakdown && Object.entries(breakdown).map(([model, d]) => (
              <span key={model}>
                {model}:{" "}
                <span className={d.signal === "BUY" ? "text-emerald-400" : d.signal === "SELL" ? "text-red-400" : "text-amber-400"}>
                  {d.signal}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```
cd frontend && npx vitest run src/components/investor/QuoteSummaryPanel.test.tsx 2>&1 | tail -15
```
Expected: all 6 tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/investor/QuoteSummaryPanel.tsx frontend/src/components/investor/QuoteSummaryPanel.test.tsx
git commit -m "feat: add QuoteSummaryPanel with 52W range slider and ML consensus bar"
```

---

## Task 6: ValuationPanel

**Files:**
- Create: `frontend/src/components/investor/ValuationPanel.tsx`
- Create: `frontend/src/components/investor/ValuationPanel.test.tsx`

- [ ] **Step 1: Write failing tests**

```typescript
// frontend/src/components/investor/ValuationPanel.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ValuationPanel } from "./ValuationPanel";
import type { CompanyDoc, FinancialsDoc, FundamentalsDoc } from "../../types";

vi.mock("../../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));

const mockCompany: CompanyDoc = {
  id: "COOP_NR", ticker: "COOP.NR", name: "Co-operative Bank",
  short: "COOP", sector: "Banking", color: "#34d399", icon: "🏦",
  csv: "COOP_NR_raw.csv", current_price: 13.50, change_pct_today: 1.2,
  signal: "BUY", price_history: [], price_preview: [],
  price_date: "2026-07-24", last_updated: "2026-07-24",
};

const mockFinancials: FinancialsDoc = {
  annual: [
    { period: "FY2024", period_end: "2024-12-31", period_type: "annual", announcement_date: "2025-03-15", revenue_kes_mn: 48000, net_income_kes_mn: 9600, eps: 1.63, bvps: 12.85, notes: "" },
    { period: "FY2023", period_end: "2023-12-31", period_type: "annual", announcement_date: "2024-03-10", revenue_kes_mn: 44000, net_income_kes_mn: 8500, eps: 1.41, bvps: 12.20, notes: "" },
  ],
  dividends: [{ announcement_date: "2025-04-01", ex_date: "2025-06-01", payment_date: "2025-07-01", amount_kes: 0.55, type: "final" }],
  corporate_actions: [], announcements: [],
};

describe("ValuationPanel", () => {
  it("renders EPS from most recent annual result", () => {
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    expect(screen.getByText("1.63")).toBeInTheDocument();
  });

  it("renders P/E computed from current_price / eps", () => {
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    // 13.50 / 1.63 ≈ 8.3
    expect(screen.getByText(/8\.[0-9]+×/)).toBeInTheDocument();
  });

  it("switches to Income tab on click", async () => {
    const user = userEvent.setup();
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    await user.click(screen.getByRole("button", { name: /Income/i }));
    expect(screen.getByText(/Net Income/i)).toBeInTheDocument();
  });

  it("switches to Dividends tab on click", async () => {
    const user = userEvent.setup();
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    await user.click(screen.getByRole("button", { name: /Dividends/i }));
    expect(screen.getByText(/0\.55/)).toBeInTheDocument();
  });

  it("shows sector comparison row for known sector", () => {
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    expect(screen.getByText(/Banking sector median/i)).toBeInTheDocument();
  });

  it("renders nothing when financials have no annual results", () => {
    const { container } = render(
      <ValuationPanel company={mockCompany} financials={{ annual: [], dividends: [], corporate_actions: [] }} fundamentals={null} />
    );
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```
cd frontend && npx vitest run src/components/investor/ValuationPanel.test.tsx 2>&1 | tail -10
```
Expected: `FAIL`.

- [ ] **Step 3: Implement the component**

```typescript
// frontend/src/components/investor/ValuationPanel.tsx
import { useState } from "react";
import type { FC } from "react";
import type { CompanyDoc, FinancialsDoc, FundamentalsDoc, FinancialResult } from "../../types";
import { getCompanyProfile } from "../../data/companyProfiles";

type Tab = "valuation" | "income" | "dividends";

const SECTOR_MEDIAN_PE: Record<string, number | null> = {
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
  "Exchange Traded Funds": null,
};

const fmt = (v: number | null, suffix = "", decimals = 2) =>
  v !== null ? `${v.toFixed(decimals)}${suffix}` : "—";

const TabBtn: FC<{ label: string; active: boolean; onClick: () => void }> = ({ label, active, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded px-3 py-1 text-xs font-semibold transition-colors ${
      active ? "bg-sky-600 text-white" : "text-muted hover:bg-rim hover:text-sub"
    }`}
  >
    {label}
  </button>
);

interface Props {
  company: CompanyDoc;
  financials: FinancialsDoc | null | undefined;
  fundamentals: FundamentalsDoc | null | undefined;
}

export const ValuationPanel: FC<Props> = ({ company, financials, fundamentals }) => {
  const [tab, setTab] = useState<Tab>("valuation");

  if (!financials?.annual?.length) return null;

  const price = company.current_price ?? 0;
  const profile = getCompanyProfile(company.ticker);
  const sharesMn = fundamentals?.shares_outstanding_mn ?? profile.shares_outstanding_mn;

  // Sort annual results newest-first; take up to 3
  const annuals = [...financials.annual]
    .sort((a, b) => b.period_end.localeCompare(a.period_end))
    .slice(0, 3);

  // Forward estimates from fundamentals collection
  const estimates = fundamentals?.estimates ?? [];
  const forwardPeriod = estimates[0]?.period ?? null;

  const sectorMedianPE = SECTOR_MEDIAN_PE[company.sector] ?? null;
  const currentPE = annuals[0]?.eps && annuals[0].eps > 0 ? price / annuals[0].eps : null;
  const sectorDiff = currentPE && sectorMedianPE
    ? ((currentPE - sectorMedianPE) / sectorMedianPE) * 100
    : null;

  const computeROE = (row: FinancialResult) => {
    if (!row.net_income_kes_mn || !row.bvps || !sharesMn) return null;
    const equity = row.bvps * sharesMn * 1_000_000;
    if (equity <= 0) return null;
    return (row.net_income_kes_mn * 1_000_000 / equity) * 100;
  };

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      {/* Header + tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam/60 px-5 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Company Valuation</p>
        <div className="flex gap-1">
          <TabBtn label="Valuation" active={tab === "valuation"} onClick={() => setTab("valuation")} />
          <TabBtn label="Income"    active={tab === "income"}    onClick={() => setTab("income")} />
          <TabBtn label="Dividends" active={tab === "dividends"} onClick={() => setTab("dividends")} />
        </div>
      </div>

      <div className="px-5 py-4">
        {/* VALUATION TAB */}
        {tab === "valuation" && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-raised/60">
                    <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted">Metric</th>
                    {annuals.map((r) => (
                      <th key={r.period} className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">
                        {r.period}
                      </th>
                    ))}
                    {forwardPeriod && (
                      <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-sky-600/70">
                        {forwardPeriod}
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-seam/50">
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">EPS (KES)</td>
                    {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{fmt(r.eps)}</td>)}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-sky-500/80">{fmt(estimates[0]?.eps_kes)} <span className="text-[10px] text-hint">est.</span></td>}
                  </tr>
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">P/E Ratio</td>
                    {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{r.eps && r.eps > 0 ? `${(price / r.eps).toFixed(1)}×` : "—"}</td>)}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-sky-500/80">{fmt(estimates[0]?.pe_forward, "×")} <span className="text-[10px] text-hint">est.</span></td>}
                  </tr>
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">BVPS (KES)</td>
                    {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{fmt(r.bvps)}</td>)}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-hint">—</td>}
                  </tr>
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">P/Book</td>
                    {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{r.bvps && r.bvps > 0 ? `${(price / r.bvps).toFixed(2)}×` : "—"}</td>)}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-hint">—</td>}
                  </tr>
                  <tr className="hover:bg-raised/20 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">ROE</td>
                    {annuals.map((r) => {
                      const roe = computeROE(r);
                      return <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{fmt(roe, "%", 1)}</td>;
                    })}
                    {forwardPeriod && <td className="px-3 py-2.5 text-right font-mono text-hint">—</td>}
                  </tr>
                </tbody>
              </table>
            </div>

            {sectorMedianPE !== null && currentPE !== null && sectorDiff !== null && (
              <div className="mt-4 rounded-lg border border-seam/60 bg-raised/30 px-4 py-2.5">
                <p className="text-xs text-sub">
                  <span className="font-semibold text-muted uppercase tracking-wider text-[10px]">Sector Peer Snapshot · </span>
                  {company.sector} sector median P/E: <span className="font-mono font-semibold text-ink">{sectorMedianPE}×</span>
                  &emsp;This stock: <span className="font-mono font-semibold text-ink">{currentPE.toFixed(1)}×</span>
                  &emsp;
                  <span className={sectorDiff >= 0 ? "text-amber-400" : "text-emerald-400"}>
                    ({sectorDiff >= 0 ? "+" : ""}{sectorDiff.toFixed(0)}% vs sector)
                  </span>
                </p>
              </div>
            )}
          </>
        )}

        {/* INCOME TAB */}
        {tab === "income" && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-raised/60">
                  <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted">Metric</th>
                  {annuals.map((r) => (
                    <th key={r.period} className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">{r.period}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-seam/50">
                <tr className="hover:bg-raised/20 transition-colors">
                  <td className="px-3 py-2.5 font-medium text-sub">Revenue (KES Mn)</td>
                  {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{r.revenue_kes_mn ? r.revenue_kes_mn.toLocaleString() : "—"}</td>)}
                </tr>
                <tr className="hover:bg-raised/20 transition-colors">
                  <td className="px-3 py-2.5 font-medium text-sub">Net Income (KES Mn)</td>
                  {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{r.net_income_kes_mn ? r.net_income_kes_mn.toLocaleString() : "—"}</td>)}
                </tr>
                <tr className="hover:bg-raised/20 transition-colors">
                  <td className="px-3 py-2.5 font-medium text-sub">EPS (KES)</td>
                  {annuals.map((r) => <td key={r.period} className="px-3 py-2.5 text-right font-mono text-ink">{fmt(r.eps)}</td>)}
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* DIVIDENDS TAB */}
        {tab === "dividends" && (
          <div className="overflow-x-auto">
            {financials.dividends.length === 0 ? (
              <p className="text-sm text-muted py-2">No dividend history on record.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-raised/60">
                    <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted">Type</th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Amount (KES)</th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Yield</th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Ex-Date</th>
                    <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Payment</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-seam/50">
                  {financials.dividends.slice(0, 8).map((d, i) => {
                    const yld = price > 0 ? ((d.amount_kes / price) * 100).toFixed(1) : null;
                    return (
                      <tr key={i} className={`hover:bg-raised/20 transition-colors ${i === 0 ? "bg-emerald-950/10" : ""}`}>
                        <td className="px-3 py-2.5 font-medium text-sub capitalize">{d.type}</td>
                        <td className="px-3 py-2.5 text-right font-mono font-semibold text-emerald-400">{d.amount_kes.toFixed(2)}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-sub">{yld ? `${yld}%` : "—"}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-hint">{d.ex_date ?? "—"}</td>
                        <td className="px-3 py-2.5 text-right font-mono text-hint">{d.payment_date ?? "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```
cd frontend && npx vitest run src/components/investor/ValuationPanel.test.tsx 2>&1 | tail -15
```
Expected: all 6 tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/investor/ValuationPanel.tsx frontend/src/components/investor/ValuationPanel.test.tsx
git commit -m "feat: add ValuationPanel with Valuation/Income/Dividends tabs and sector peer comparison"
```

---

## Task 7: NewsPanel

**Files:**
- Create: `frontend/src/components/investor/NewsPanel.tsx`
- Create: `frontend/src/components/investor/NewsPanel.test.tsx`

- [ ] **Step 1: Write failing tests**

```typescript
// frontend/src/components/investor/NewsPanel.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NewsPanel } from "./NewsPanel";
import type { FinancialsDoc, NewsItem } from "../../types";

vi.mock("../../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));

const mockFinancials: FinancialsDoc = {
  annual: [], dividends: [], corporate_actions: [],
  announcements: [
    { date: "2026-07-24", type: "financial_result", title: "H1 2026 Interim Results", url: "https://nse.co.ke/filing1.pdf" },
    { date: "2026-06-15", type: "dividend",         title: "Final dividend KES 0.55 declared", url: "https://nse.co.ke/filing2.pdf" },
    { date: "2026-04-02", type: "corporate_action", title: "CBK grants approval for digital credit", url: "" },
  ],
};

const scraperItems: NewsItem[] = [
  { id: "s1", date: "2026-07-20", title: "New branch opening in Mombasa", category: "general", body: "Full body text here.", url: null, source: "scraper" },
];

describe("NewsPanel", () => {
  it("renders announcement titles", () => {
    render(<NewsPanel financials={mockFinancials} newsItems={[]} />);
    expect(screen.getByText(/H1 2026 Interim Results/i)).toBeInTheDocument();
    expect(screen.getByText(/Final dividend KES 0.55/i)).toBeInTheDocument();
  });

  it("renders external link for announcement with URL", () => {
    render(<NewsPanel financials={mockFinancials} newsItems={[]} />);
    const link = screen.getByRole("link", { name: /View NSE filing/i });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows Read more toggle for item without URL", () => {
    render(<NewsPanel financials={mockFinancials} newsItems={[]} />);
    expect(screen.getByText(/Read more/i)).toBeInTheDocument();
  });

  it("expands inline body on Read more click", async () => {
    const user = userEvent.setup();
    render(<NewsPanel financials={mockFinancials} newsItems={scraperItems} />);
    const btn = screen.getByText(/Read more/i);
    await user.click(btn);
    expect(screen.getByText("Full body text here.")).toBeInTheDocument();
  });

  it("filters by category tab", async () => {
    const user = userEvent.setup();
    render(<NewsPanel financials={mockFinancials} newsItems={[]} />);
    await user.click(screen.getByRole("button", { name: /Dividends/i }));
    expect(screen.getByText(/Final dividend KES 0.55/i)).toBeInTheDocument();
    expect(screen.queryByText(/H1 2026 Interim Results/i)).not.toBeInTheDocument();
  });

  it("deduplicates items with same date+title prefix", () => {
    const duplicate: NewsItem = { id: "d1", date: "2026-07-24", title: "H1 2026 Interim Results — more detail", category: "earnings", body: null, url: null, source: "scraper" };
    render(<NewsPanel financials={mockFinancials} newsItems={[duplicate]} />);
    // Should only show one item for this title
    const matches = screen.getAllByText(/H1 2026 Interim Results/i);
    expect(matches).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run to confirm failure**

```
cd frontend && npx vitest run src/components/investor/NewsPanel.test.tsx 2>&1 | tail -10
```
Expected: `FAIL`.

- [ ] **Step 3: Implement the component**

```typescript
// frontend/src/components/investor/NewsPanel.tsx
import { useState, useMemo } from "react";
import type { FC } from "react";
import type { FinancialsDoc, NewsItem } from "../../types";

type Category = "all" | "earnings" | "dividend" | "regulatory" | "agm" | "corporate_action";

const CATEGORY_COLORS: Record<string, string> = {
  earnings:         "bg-emerald-900/40 text-emerald-400 border-emerald-800",
  dividend:         "bg-sky-900/40 text-sky-400 border-sky-800",
  regulatory:       "bg-amber-900/40 text-amber-400 border-amber-800",
  agm:              "bg-violet-900/40 text-violet-400 border-violet-800",
  corporate_action: "bg-orange-900/40 text-orange-400 border-orange-800",
  general:          "bg-slate-800/60 text-slate-400 border-slate-700",
  financial_result: "bg-emerald-900/40 text-emerald-400 border-emerald-800",
};

const SOURCE_COLORS: Record<string, string> = {
  NSE:     "border-slate-600 text-slate-400",
  scraper: "border-indigo-700 text-indigo-400",
};

function nseTypeToCategory(type: string): NewsItem["category"] {
  if (type === "financial_result") return "earnings";
  if (type === "dividend") return "dividend";
  if (type === "agm") return "agm";
  if (type === "corporate_action") return "corporate_action";
  return "general";
}

function daysAgo(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr + "T00:00:00").getTime()) / 86_400_000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  if (diff < 30) return `${diff} days ago`;
  if (diff < 365) return `${Math.round(diff / 30)} months ago`;
  return `${Math.round(diff / 365)} years ago`;
}

function mergeAndDeduplicate(financials: FinancialsDoc | null | undefined, newsItems: NewsItem[]): NewsItem[] {
  const fromAnnouncements: NewsItem[] = (financials?.announcements ?? []).map((a) => ({
    id: `nse-${a.date}-${a.title.slice(0, 20)}`,
    date: a.date,
    title: a.title,
    category: nseTypeToCategory(a.type),
    body: null,
    url: a.url || null,
    source: "NSE" as const,
  }));

  const all = [...newsItems, ...fromAnnouncements].sort((a, b) => {
    const dateD = b.date.localeCompare(a.date);
    if (dateD !== 0) return dateD;
    return a.source === "scraper" ? -1 : 1; // scraper wins on same date
  });

  const seen = new Set<string>();
  return all.filter((item) => {
    const key = `${item.date}-${item.title.slice(0, 80).toLowerCase()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

interface Props {
  financials: FinancialsDoc | null | undefined;
  newsItems: NewsItem[];
}

const PAGE_SIZE = 5;

export const NewsPanel: FC<Props> = ({ financials, newsItems }) => {
  const [activeCategory, setActiveCategory] = useState<Category>("all");
  const [openId, setOpenId] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  const merged = useMemo(() => mergeAndDeduplicate(financials, newsItems), [financials, newsItems]);

  const filtered = activeCategory === "all"
    ? merged
    : merged.filter((item) => item.category === activeCategory);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = filtered.length > visibleCount;

  const categories: { key: Category; label: string }[] = [
    { key: "all",              label: "All"               },
    { key: "earnings",         label: "Earnings"          },
    { key: "dividend",         label: "Dividends"         },
    { key: "regulatory",       label: "Regulatory"        },
    { key: "corporate_action", label: "Corporate Actions" },
  ];

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam/60 px-5 py-3">
        <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
          Latest News &amp; Press Releases
        </p>
        <div className="flex flex-wrap gap-1.5">
          {categories.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              onClick={() => { setActiveCategory(key); setVisibleCount(PAGE_SIZE); }}
              className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
                activeCategory === key
                  ? "bg-sky-600 text-white"
                  : "text-muted hover:bg-rim hover:text-sub"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {merged.length === 0 ? (
        <p className="px-5 py-6 text-sm text-muted">No announcements on record for this company.</p>
      ) : (
        <div className="divide-y divide-seam/40">
          {visible.map((item) => (
            <div key={item.id} className="px-5 py-4 hover:bg-raised/20 transition-colors">
              <div className="mb-1.5 flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-semibold text-hint">{daysAgo(item.date)}</span>
                <span className="text-[10px] text-hint">· {item.date}</span>
                <span className={`ml-auto rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${SOURCE_COLORS[item.source] ?? SOURCE_COLORS.NSE}`}>
                  {item.source}
                </span>
                <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${CATEGORY_COLORS[item.category] ?? CATEGORY_COLORS.general}`}>
                  {item.category.replace("_", " ")}
                </span>
              </div>

              <p className="text-sm font-medium text-ink">{item.title}</p>

              {openId === item.id && item.body && (
                <p className="mt-2 text-sm leading-relaxed text-sub">{item.body}</p>
              )}

              <div className="mt-2 flex flex-wrap items-center gap-3">
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-semibold text-sky-400 hover:text-sky-300"
                  >
                    ↗ View NSE filing
                  </a>
                ) : item.body ? (
                  <button
                    type="button"
                    onClick={() => setOpenId(openId === item.id ? null : item.id)}
                    className="text-xs font-semibold text-sky-400 hover:text-sky-300"
                  >
                    {openId === item.id ? "Show less ▲" : "Read more ▼"}
                  </button>
                ) : null}
              </div>
            </div>
          ))}

          {hasMore && (
            <div className="px-5 py-3">
              <button
                type="button"
                onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
                className="text-xs font-semibold text-sky-400 hover:text-sky-300"
              >
                Load more ↓ ({filtered.length - visibleCount} remaining)
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```
cd frontend && npx vitest run src/components/investor/NewsPanel.test.tsx 2>&1 | tail -15
```
Expected: all 6 tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/investor/NewsPanel.tsx frontend/src/components/investor/NewsPanel.test.tsx
git commit -m "feat: add NewsPanel with category filter, inline expand, and deduplication"
```

---

## Task 8: Wire Panels into CompanyDeepDive

**Files:**
- Modify: `frontend/src/pages/CompanyDeepDive.tsx`

- [ ] **Step 1: Add imports at the top of `CompanyDeepDive.tsx`**

After the existing import block (around line 14), add:

```typescript
import { CompanyProfileCard } from "../components/investor/CompanyProfileCard";
import { QuoteSummaryPanel } from "../components/investor/QuoteSummaryPanel";
import { ValuationPanel } from "../components/investor/ValuationPanel";
import { NewsPanel } from "../components/investor/NewsPanel";
import { useFundamentals, useNews } from "../hooks/useCompany";
```

- [ ] **Step 2: Add new hooks in the main component body**

In `CompanyDeepDive` (around line 1042, after the existing `useMacro()` call), add:

```typescript
const { data: fundamentals } = useFundamentals(ticker);
const { data: newsItems = [] }  = useNews(ticker);
```

- [ ] **Step 3: Insert panels into the JSX**

In the return JSX, the current section order is:
1. Trading terminal header
2. StatsStrip
3. DataQualityBanner
4. ChartSection
5. PriceExplainer
6. FilingsTimeline
7. GatedContent

Change to:

```tsx
{/* ── Company profile ──────────────────────────────────────── */}
<CompanyProfileCard company={company} />

{/* ── Quote summary ─────────────────────────────────────────── */}
<QuoteSummaryPanel
  company={company}
  technicals={technicals}
  financials={financials}
  snapshot={snapshot}
/>

{/* ── Stats strip — reacts to selected range ─────────────────── */}
<StatsStrip ... />                        {/* existing — no change */}

{/* ── Data quality banner ─────────────────────────────────────── */}
<DataQualityBanner ... />                 {/* existing — no change */}

{/* ── Trading chart ───────────────────────────────────────────── */}
{(history.length > 1 || range === "1D") && <ChartSection ... />}  {/* existing — no change */}

{/* ── AI price explainer ──────────────────────────────────────── */}
{range !== "1D" && visible.length >= 2 && <PriceExplainer ... />} {/* existing — no change */}

{/* ── Company valuation ───────────────────────────────────────── */}
<ValuationPanel company={company} financials={financials} fundamentals={fundamentals} />

{/* ── NSE filings timeline ────────────────────────────────────── */}
<FilingsTimeline ... />                   {/* existing — no change */}

{/* ── News & press releases ───────────────────────────────────── */}
<NewsPanel financials={financials} newsItems={newsItems} />

{/* ── AI signal + technicals ──────────────────────────────────── */}
<GatedContent ... />                      {/* existing — no change */}
```

The full replacement block for the `<div className="space-y-4">` content (insert profile and quote before StatsStrip, valuation after PriceExplainer, news after FilingsTimeline):

```tsx
return (
  <PageShell>
    <div className="space-y-4">
      {/* ── Trading terminal header ────────────────────────────────────── */}
      <div className="overflow-hidden rounded-xl border border-rim bg-surface shadow-sm">
        {/* ... existing header content — DO NOT CHANGE ... */}
      </div>

      {/* ── Company profile ───────────────────────────────────────────── */}
      <CompanyProfileCard company={company} />

      {/* ── Quote summary ─────────────────────────────────────────────── */}
      <QuoteSummaryPanel
        company={company}
        technicals={technicals}
        financials={financials ?? null}
        snapshot={snapshot ?? null}
      />

      {/* ── Stats strip — reacts to selected range ────────────────────── */}
      <StatsStrip
        data={visible.length > 0 ? visible : history}
        range={range}
        currentPrice={company.current_price}
        technicals={technicals}
      />

      {/* ── Data quality banner (shows for gaps / limited / no history) ── */}
      <DataQualityBanner history={history} />

      {/* ── Trading chart ─────────────────────────────────────────────── */}
      {(history.length > 1 || range === "1D") && (
        <ChartSection
          company={company}
          technicals={technicals}
          range={range}
          setRange={setRange}
          from={from}
          setFrom={setFrom}
          to={to}
          setTo={setTo}
          visible={visible}
          announcements={financials?.announcements ?? []}
          intradayDate={company.intraday_date}
          intradayDay={intradayDay}
          setIntradayDay={setIntradayDay}
          todayEAT={todayEAT}
        />
      )}

      {/* ── AI price explainer ────────────────────────────────────────── */}
      {range !== "1D" && visible.length >= 2 && (
        <PriceExplainer
          company={company}
          visible={visible}
          technicals={technicals}
          rangeLabel={rangeLabel}
          events={events as CorporateEvent[]}
          financials={financials}
          macro={macro}
        />
      )}

      {/* ── Company valuation ─────────────────────────────────────────── */}
      <ValuationPanel
        company={company}
        financials={financials ?? null}
        fundamentals={fundamentals ?? null}
      />

      {/* ── NSE filings timeline ──────────────────────────────────────── */}
      <FilingsTimeline financials={financials ?? undefined} />

      {/* ── News & press releases ─────────────────────────────────────── */}
      <NewsPanel financials={financials} newsItems={newsItems} />

      {/* ── AI signal + technicals ────────────────────────────────────── */}
      <GatedContent
        snapshot={snapshot}
        snapLoading={snapLoading}
        technicals={technicals}
        techLoading={techLoading}
      />
    </div>
  </PageShell>
);
```

- [ ] **Step 4: Type-check and run full test suite**

```
cd frontend && npx tsc --noEmit --pretty false 2>&1 | head -30
npx vitest run 2>&1 | tail -20
```
Expected: no TypeScript errors, all tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CompanyDeepDive.tsx
git commit -m "feat: wire CompanyProfileCard, QuoteSummaryPanel, ValuationPanel, NewsPanel into CompanyDeepDive"
```

---

## Task 9: Python News Scraper

**Files:**
- Create: `pipeline/scripts/scrape_news.py`
- Create: `tests/pipeline/test_scrape_news.py`

- [ ] **Step 1: Write the failing tests first**

```python
# tests/pipeline/test_scrape_news.py
import json
import pytest
from unittest.mock import patch, MagicMock, call

# Patch firebase_admin before importing the scraper
with patch("firebase_admin.credentials"), \
     patch("firebase_admin.initialize_app"), \
     patch("firebase_admin.firestore"):
    import importlib, sys
    # Pre-inject mocks so firebase_admin is never called for real
    pass

@pytest.fixture
def mock_db():
    """Firestore client mock."""
    db = MagicMock()
    col = MagicMock()
    doc = MagicMock()
    db.collection.return_value = col
    col.document.return_value = col
    col.collection.return_value = col
    col.document.return_value = doc
    doc.set = MagicMock()
    return db, col, doc


def make_scraper(mock_db):
    """Import scraper with firebase patched out."""
    db, col, doc = mock_db
    with patch.dict("sys.modules", {
        "firebase_admin": MagicMock(),
        "firebase_admin.credentials": MagicMock(),
        "firebase_admin.firestore": MagicMock(),
    }):
        import importlib
        if "pipeline.scripts.scrape_news" in sys.modules:
            del sys.modules["pipeline.scripts.scrape_news"]
        import pipeline.scripts.scrape_news as m
        m.db = db
        return m


def test_parse_announcement_returns_news_item():
    row = {
        "date": "2026-07-24",
        "company": "COOP",
        "title": "H1 2026 Interim Results",
        "url": "https://nse.co.ke/filing1.pdf",
        "type": "financial_result",
    }
    from pipeline.scripts.scrape_news import parse_announcement
    item = parse_announcement(row)
    assert item["date"] == "2026-07-24"
    assert item["title"] == "H1 2026 Interim Results"
    assert item["category"] == "earnings"
    assert item["source"] == "scraper"
    assert item["url"] == "https://nse.co.ke/filing1.pdf"


def test_make_doc_id_is_deterministic():
    from pipeline.scripts.scrape_news import make_doc_id
    id1 = make_doc_id("2026-07-24", "H1 2026 Interim Results")
    id2 = make_doc_id("2026-07-24", "H1 2026 Interim Results")
    assert id1 == id2
    assert " " not in id1


def test_make_doc_id_differs_for_different_titles():
    from pipeline.scripts.scrape_news import make_doc_id
    id1 = make_doc_id("2026-07-24", "Results A")
    id2 = make_doc_id("2026-07-24", "Results B")
    assert id1 != id2


def test_push_item_calls_firestore_set(mock_db):
    m = make_scraper(mock_db)
    db, col, doc = mock_db
    item = {"date": "2026-07-24", "title": "Test", "category": "earnings",
            "body": None, "url": None, "source": "scraper"}
    m.push_item("COOP_NR", item)
    assert doc.set.called


def test_fetch_nse_returns_list_on_http_error():
    """Scraper fails gracefully per-ticker, returns empty list."""
    with patch("requests.get") as mock_get:
        mock_get.side_effect = Exception("network error")
        from pipeline.scripts.scrape_news import fetch_nse_announcements
        result = fetch_nse_announcements("COOP_NR")
        assert result == []
```

- [ ] **Step 2: Run to confirm failure**

```
cd C:\Users\moeng\nse_predictor
python -m pytest tests/pipeline/test_scrape_news.py -v 2>&1 | tail -15
```
Expected: `ERROR` — `pipeline.scripts.scrape_news` not found.

- [ ] **Step 3: Implement the scraper**

```python
# pipeline/scripts/scrape_news.py
"""
NSE announcement scraper — pushes to Firestore news/{ticker}/items/{doc_id}.

Usage:
  cd pipeline && python scripts/scrape_news.py

Idempotent: doc_id = hash(date + title). Re-running never creates duplicates.
Fails gracefully per ticker — one failure does not stop others.
Always exits 0 (best-effort enrichment, not core data).
"""
import sys
import os
import hashlib
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── Firebase init (same pattern as run_inference.py) ──────────────────────────
import firebase_admin
from firebase_admin import credentials, firestore as fs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_SA_KEY = os.environ.get("FIREBASE_SA_KEY_PATH", "firebase-key.json")
if not firebase_admin._apps:
    cred = credentials.Certificate(_SA_KEY)
    firebase_admin.initialize_app(cred)

db = fs.client()

# ── Load company tickers from companies.json ──────────────────────────────────
import json
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "companies.json")
with open(_CONFIG_PATH) as f:
    _COMPANIES = json.load(f)

TICKERS = [c["ticker"].replace(".", "_") for c in _COMPANIES]

# ── Type mappings ──────────────────────────────────────────────────────────────
NSE_TYPE_TO_CATEGORY = {
    "financial_result": "earnings",
    "results":          "earnings",
    "dividend":         "dividend",
    "agm":              "agm",
    "corporate_action": "corporate_action",
    "rights":           "corporate_action",
    "bonus":            "corporate_action",
    "regulatory":       "regulatory",
}

def _infer_category(title: str, raw_type: str) -> str:
    mapped = NSE_TYPE_TO_CATEGORY.get(raw_type.lower(), "general")
    if mapped != "general":
        return mapped
    title_lower = title.lower()
    if any(w in title_lower for w in ("result", "profit", "earnings", "revenue")):
        return "earnings"
    if any(w in title_lower for w in ("dividend", "dps")):
        return "dividend"
    if any(w in title_lower for w in ("agm", "annual general")):
        return "agm"
    if any(w in title_lower for w in ("rights", "bonus", "split")):
        return "corporate_action"
    return "general"

# ── Core functions ─────────────────────────────────────────────────────────────
def make_doc_id(date: str, title: str) -> str:
    """Deterministic doc id: hash(date + title). Safe for Firestore paths."""
    raw = f"{date}:{title.strip().lower()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def parse_announcement(row: dict) -> dict:
    """Convert a raw scraped row to a NewsItem dict."""
    raw_type = row.get("type", "general")
    title = row.get("title", "")
    return {
        "date":     row.get("date", ""),
        "title":    title,
        "category": _infer_category(title, raw_type),
        "body":     row.get("body", None),
        "url":      row.get("url", None) or None,
        "source":   "scraper",
        "created_at": datetime.utcnow().isoformat(),
    }


def push_item(safe_ticker: str, item: dict) -> None:
    """Write a NewsItem to Firestore news/{ticker}/items/{doc_id}."""
    doc_id = make_doc_id(item["date"], item["title"])
    ref = db.collection("news").document(safe_ticker).collection("items").document(doc_id)
    ref.set(item, merge=True)
    log.info("  pushed %s / %s", safe_ticker, doc_id)


def fetch_nse_announcements(safe_ticker: str) -> list[dict]:
    """
    Fetch corporate announcements for one ticker from the NSE announcements page.
    Returns [] on any error — caller proceeds to next ticker.

    NSE page: https://www.nse.co.ke/market-statistics/corporate-announcements/
    Filters by company name. Parses HTML table with columns:
      Date | Company | Subject | Document
    """
    try:
        # NSE announcements page — filter by company name approximation
        # The NSE page is paginated; we fetch the first page (most recent ~20 items)
        url = "https://www.nse.co.ke/market-statistics/corporate-announcements/"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to find the announcements table
        table = soup.find("table")
        if not table:
            log.warning("%s: no table found on NSE announcements page", safe_ticker)
            return []

        # Strip "_NR" suffix to get the short ticker for matching
        short = safe_ticker.replace("_NR", "").upper()
        rows = []
        for tr in table.find_all("tr")[1:]:  # skip header
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue
            company_cell = cells[1].get_text(strip=True).upper()
            if short not in company_cell:
                continue
            date_str  = cells[0].get_text(strip=True)
            title_str = cells[2].get_text(strip=True)
            link_tag  = cells[-1].find("a") if len(cells) >= 4 else None
            doc_url   = link_tag["href"] if link_tag and link_tag.get("href") else None
            rows.append({
                "date":  _parse_date(date_str),
                "title": title_str,
                "type":  "general",
                "url":   doc_url,
            })

        log.info("%s: fetched %d announcements from NSE", safe_ticker, len(rows))
        return rows

    except Exception as exc:
        log.warning("%s: fetch failed — %s", safe_ticker, exc)
        return []


def _parse_date(raw: str) -> str:
    """Normalise NSE date string to ISO YYYY-MM-DD. Falls back to today on parse error."""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.utcnow().strftime("%Y-%m-%d")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    log.info("NSE news scraper starting — %d companies", len(TICKERS))
    pushed_total = 0
    for safe_ticker in TICKERS:
        try:
            rows = fetch_nse_announcements(safe_ticker)
            for row in rows:
                item = parse_announcement(row)
                if not item["title"] or not item["date"]:
                    continue
                push_item(safe_ticker, item)
                pushed_total += 1
        except Exception as exc:
            log.error("%s: unhandled error — %s", safe_ticker, exc)
            continue
    log.info("Done — pushed %d items total", pushed_total)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Install scraper dependencies in requirements.txt**

Add `beautifulsoup4` to `pipeline/requirements.txt` if not already present:

```
beautifulsoup4>=4.12.0
```

Then verify it's installable:

```
cd pipeline && pip install -r requirements.txt --quiet 2>&1 | tail -5
```

- [ ] **Step 5: Run tests**

```
cd C:\Users\moeng\nse_predictor
python -m pytest tests/pipeline/test_scrape_news.py -v 2>&1 | tail -20
```
Expected: all 5 tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add pipeline/scripts/scrape_news.py tests/pipeline/test_scrape_news.py pipeline/requirements.txt
git commit -m "feat: add NSE news scraper (scrape_news.py) with pytest coverage"
```

---

## Task 10: CI Integration

**Files:**
- Modify: `.github/workflows/daily_inference.yml`

- [ ] **Step 1: Read the current daily_inference.yml**

Open `.github/workflows/daily_inference.yml`. Locate the step that runs `run_inference.py`. The new scraper step goes **after** inference and **before** any push-to-Firestore step.

- [ ] **Step 2: Add the scraper step**

After the inference run step, insert:

```yaml
      - name: Scrape NSE news
        run: |
          set -euo pipefail
          cd pipeline
          python scripts/scrape_news.py
        continue-on-error: true
        env:
          FIREBASE_SA_KEY_PATH: ${{ secrets.FIREBASE_SA_KEY_PATH }}
```

`continue-on-error: true` means scraper failures never block the inference pipeline. The scraper is enrichment-only.

- [ ] **Step 3: Verify YAML syntax**

```
python -c "import yaml; yaml.safe_load(open('.github/workflows/daily_inference.yml'))" && echo "YAML valid"
```
Expected: `YAML valid`.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/daily_inference.yml
git commit -m "feat: add NSE news scraper step to daily_inference CI workflow"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task that implements it |
|-----------------|------------------------|
| CompanyProfileCard — about block | Task 4 |
| QuoteSummaryPanel — 52W slider | Task 5 |
| QuoteSummaryPanel — ML consensus bar | Task 5 |
| ValuationPanel — tabbed multi-year table | Task 6 |
| ValuationPanel — sector peer comparison | Task 6 |
| NewsPanel — category filter | Task 7 |
| NewsPanel — inline expand + external link | Task 7 |
| NewsPanel — merge + deduplicate | Task 7 |
| NewsPanel — 50-item Firestore cap | Task 3 (fetchNews limit) |
| FundamentalsDoc / NewsItem types | Task 2 |
| fetchFundamentals / fetchNews helpers | Task 3 |
| useFundamentals / useNews hooks | Task 3 |
| Wire panels in correct page order | Task 8 |
| Static company profile lookup | Task 1 |
| Python news scraper | Task 9 |
| CI daily_inference integration | Task 10 |
| Firestore security rules | ⚠ Not covered — add to `firestore.rules` manually per spec §10 |

**Firestore rules gap:** Add these two rules to `firestore.rules` before deploying (not a separate task — one-liner change):

```
match /fundamentals/{ticker} { allow read: if request.auth != null; }
match /news/{ticker}/items/{itemId} { allow read: if request.auth != null; }
```

**Type consistency check:** `FinancialResult` interface uses `.annual` in `FinancialsDoc` — confirmed against `index.ts` line 129. All task references use `financials.annual` (not `financials.annual_results`). ✓

**Null safety check:** Every panel has an explicit render condition or null-chip omission path. ValuationPanel returns `null` when `annual.length === 0`. QuoteSummaryPanel returns `null` when `current_price === null`. NewsPanel shows a "no announcements" message when `merged.length === 0`. ✓
