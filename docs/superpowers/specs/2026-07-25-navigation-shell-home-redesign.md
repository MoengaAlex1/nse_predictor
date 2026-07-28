# Navigation Shell & Home Page Redesign — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the NSE predictor from a minimal 3-card dashboard into a MarketScreener-style financial intelligence portal — sticky header with multi-tier nav, auto-scrolling ticker tape, global search with autocomplete, and a two-column home page with market tables, sector performance, and sentiment panels.

**Architecture:** Approach B — replace `Navbar.tsx` + `PageShell.tsx` with a single `AppShell.tsx` that all three routes share. Home page is rebuilt as a two-column layout composed of focused sub-components. No new Firestore collections required — all data comes from existing `market_overview` and `companies` hooks.

**Tech Stack:** React 19, TypeScript, Tailwind CSS v3, Recharts v3, TanStack Query, React Router v6, Firebase/Firestore.

---

## Sub-project Scope

This spec covers two tightly coupled sub-projects:
1. **Navigation & Shell** — `AppShell`, `TickerTape`, `GlobalSearch`, brand logo mark
2. **Home page redesign** — two-column layout with 7 focused panels

Sub-projects 3–6 (Screener upgrade, Company detail enhancements, Calendar, Portfolio) are out of scope.

---

## File Map

### Deleted
| File | Replaced by |
|------|------------|
| `src/components/layout/Navbar.tsx` | `AppShell.tsx` |
| `src/components/layout/PageShell.tsx` | `AppShell.tsx` |

### Created
| File | Responsibility |
|------|---------------|
| `src/components/layout/AppShell.tsx` | Root layout wrapper: sticky header + ticker tape + `<main>` |
| `src/components/layout/NseLogo.tsx` | Inline SVG brand mark (bull icon + wordmark) |
| `src/components/layout/TickerTape.tsx` | Auto-scrolling index + mover strip |
| `src/components/layout/GlobalSearch.tsx` | Expanding search box with autocomplete dropdown |
| `src/components/layout/ThemeToggle.tsx` | Extracted from old Navbar — Light/System/Dark pill |
| `src/components/layout/MobileNav.tsx` | Hamburger sheet for small screens |
| `src/pages/Home.tsx` | Full rewrite — two-column market intelligence layout |
| `src/components/home/MarketSummaryStrip.tsx` | NSE20 chip + BUY/HOLD/SELL counts + total securities |
| `src/components/home/MoversTable.tsx` | Reusable 5-row table for Gainers / Losers / Most Active |
| `src/components/home/SectorPerformance.tsx` | Horizontal bar chart from `sector_performance` |
| `src/components/home/SentimentDonut.tsx` | Recharts PieChart donut — BUY/HOLD/SELL breakdown |
| `src/components/home/TopSignals.tsx` | 5 highest-confidence BUY picks from companies list |

### Modified
| File | Change |
|------|--------|
| `src/App.tsx` | Wrap routes with `AppShell` instead of `PageShell` |
| `src/pages/Companies.tsx` | Remove internal `PageShell` wrapper (now provided by `AppShell`) |
| `src/pages/CompanyDeepDive.tsx` | Remove internal `PageShell` wrapper |

---

## Section 1: AppShell

### Structure
```
<AppShell>
  <header>          ← sticky, z-50
    <NseLogo />
    <NavLinks />    ← hidden on mobile
    <GlobalSearch />
    <ThemeToggle />
    <MobileMenuBtn /> ← visible only on mobile
  </header>
  <TickerTape />    ← sticky below header, hidden on xs
  <main>
    {children}      ← max-w-7xl, responsive px, py-6
  </main>
</AppShell>
```

### Header
- **Height:** 56px (`h-14`)
- **Sticky:** `sticky top-0 z-50 border-b border-seam bg-canvas/95 backdrop-blur`
- **Left:** `<NseLogo />` — SVG bull icon (20×20) + "NSE" bold + "Intelligence" normal weight. Navigates to `/`
- **Centre (desktop only):** Nav links — `Markets` (→ `/companies`), `Screener` (→ `/companies`, same page, phase 3 will add view param), `News` (→ `/companies`), `Calendar` (disabled, muted — phase 5). All use `NavLink` with active underline.
- **Right:** `<GlobalSearch />` icon that expands, then `<ThemeToggle />` pill
- **Mobile (`< lg`):** Nav links hidden, replaced by hamburger icon that opens `<MobileNav />` sheet

### NseLogo
- Inline SVG — no image asset required
- Bull silhouette icon in `text-accent` color
- "NSE" in `font-black text-ink`, "Intelligence" in `font-medium text-muted`
- Entire element is a `<Link to="/">`

### GlobalSearch
**Trigger state:** Shows a magnifying-glass icon button. On click, expands to a full input inline (desktop) or full-width overlay (mobile).

**Search logic:**
- Searches `useCompanies()` cache — zero extra network calls
- Matches against: `ticker`, `short`, `name` (case-insensitive substring)
- Shows up to 6 results in a dropdown positioned below the input
- Each result row: `<CompanyLogo />` (24px) | ticker badge | full name | sector chip
- Clicking a result navigates to `/company/:ticker` and closes the search
- Keyboard: `↑↓` to navigate results, `Enter` to select, `Escape` to close
- Closes on outside click (click-outside listener)

**Empty state:** "No companies match…" message
**Loading state:** Input disabled with subtle spinner while `useCompanies()` is loading

### TickerTape
- **Height:** 32px (`h-8`)
- **Visibility:** Hidden below `sm` (640px)
- **Sticky:** `sticky top-14 z-40 border-b border-seam bg-surface`
- **Animation:** CSS `@keyframes marquee` infinite horizontal scroll, ~40s per cycle. Pauses on hover (`animation-play-state: paused`).
- **Content (left to right):**
  1. **NSE20 index chip** (not a company): label "NSE 20" | value | change% with ▲/▼ arrow + color
  2. **Top gainers** from `market_overview.top_gainers`: `<CompanyLogo />` (16px) | ticker | `▲ X.X%` in emerald
  3. **Top losers** from `market_overview.top_losers`: `<CompanyLogo />` (16px) | ticker | `▼ X.X%` in red
  4. Content duplicated once so the loop appears seamless
- **Separator:** vertical pipe `|` with `text-seam` between items
- **Data source:** `useMarket()` hook (already exists, fetches `market_overview`)
- **No data:** tape hidden entirely if `market` is null

### MobileNav
- Triggered by hamburger icon in header
- Renders as a full-height sheet sliding in from the left (or a simple dropdown)
- Contains all nav links + theme toggle
- Closes on link click or outside tap

---

## Section 2: Home Page

### Layout
```
<Home>
  <MarketSummaryStrip />          ← full width, above columns
  
  <div class="lg:grid lg:grid-cols-[1fr_360px] gap-6">
    
    <!-- MAIN COLUMN -->
    <div class="space-y-5">
      <MoversTable type="gainers" />
      <MoversTable type="losers" />
      <MoversTable type="active" />
    </div>
    
    <!-- SIDEBAR -->
    <div class="space-y-5">
      <SentimentDonut />
      <SectorPerformance />
      <TopSignals />
    </div>
    
  </div>
</Home>
```

At `< lg` (1024px): sidebar stacks below main column. Order becomes: Strip → Gainers → Losers → Active → Sentiment → Sectors → Top Signals.

### MarketSummaryStrip
A compact horizontal band, full width, showing:
- **NSE 20 chip:** value + change% — from `market.nse20_value` + `market.nse20_change_pct`. Shows "N/A" if null.
- **Signal pills:** three pills — `42 BUY` (emerald), `51 HOLD` (amber), `24 SELL` (red) — from `market.signal_distribution`
- **Total:** "117 securities tracked" — from `companies.length`
- **Date:** "as of YYYY-MM-DD" from `market.date`

On mobile these wrap onto two lines. Strip has `border border-rim bg-surface rounded-xl px-5 py-3`.

### MoversTable
Reusable component, accepts `type: "gainers" | "losers" | "active"` and `companies: CompanyDoc[]`.

**Data derivation:**
- `gainers`: `market.top_gainers` joined with `companies` to get price + signal (join on ticker)
- `losers`: `market.top_losers` joined with `companies`
- `active`: `companies` sorted by `Math.abs(change_pct_today)` descending, top 5

**Columns:**
| # | Column | Value |
|---|--------|-------|
| 1 | Company | `<CompanyLogo />` (24px) + `short` name bold + `ticker` muted below |
| 2 | Price | `KES X.XX` monospace |
| 3 | Change | `+X.XX%` / `-X.XX%` colored pill |
| 4 | Signal | `<SignalBadge />` |

All rows are `<Link to="/company/:ticker">` — full row clickable.

**Table header:** Sector label pill on the left + "5 of 117" count on the right.

**Loading state:** 5 skeleton rows.

**Empty state:** "No data available" message.

On mobile: columns 2–4 stay visible; no truncation needed as data is compact.

### SentimentDonut
- Recharts `PieChart` with inner radius 40%, outer radius 65%
- Three segments: BUY (emerald `#10b981`), HOLD (amber `#f59e0b`), SELL (red `#ef4444`)
- Center label: dominant signal name + count
- No legend (colors are self-evident with existing signal system)
- Section header: "Market Sentiment"
- Data: `market.signal_distribution`

### SectorPerformance
- One horizontal bar per sector from `market.sector_performance`
- Sorted descending by performance value
- Positive bars: emerald fill; negative bars: red fill
- Each row: `[sector name]  [██████░░░░]  +2.3%`
- Bar width proportional to absolute value, capped at 100% of column width
- Section header: "Sector Performance · today"
- Data: `market.sector_performance` (Record<string, number>)

### TopSignals
- 5 companies from `companies` where `signal === "BUY"`, sorted by `change_pct_today` descending
- Each row: `<CompanyLogo />` (32px) | name + ticker | price | change% | `<SignalBadge />`
- Same row-as-link pattern as MoversTable
- Section header: "Top Buy Signals"

---

## Data Flow

```
useMarket()      → market_overview Firestore doc  → MarketSummaryStrip, TickerTape, SentimentDonut, SectorPerformance
useCompanies()   → companies Firestore collection  → GlobalSearch, MoversTable (active), TopSignals, MoversTable join
```

No new Firestore reads introduced. Both hooks are already cached by TanStack Query (5-min stale time).

---

## Responsive Breakpoints

| Breakpoint | Behaviour |
|-----------|-----------|
| `< sm` (640px) | Ticker tape hidden. Nav links hidden (hamburger only). Home stacks single column. |
| `sm–lg` (640–1024px) | Ticker tape visible. Nav links hidden (hamburger). Home stacks single column. |
| `≥ lg` (1024px+) | Full two-column home. Nav links visible. Hamburger hidden. |

---

## Styling Conventions

Follows existing project conventions:
- CSS custom property tokens: `bg-canvas`, `bg-surface`, `bg-raised`, `border-seam`, `border-rim`, `text-ink`, `text-sub`, `text-muted`, `text-hint`, `text-accent`
- Signal colors: BUY = `emerald-500`, HOLD = `amber-500`, SELL = `red-500`
- Font: `font-mono` for prices and percentages
- Positive change: `text-emerald-500`, negative: `text-red-500`
- All interactive rows have `hover:bg-raised/60 transition-colors`

---

## Out of Scope

- Live/streaming prices (ticker tape shows last `market_overview` snapshot)
- NASI / NSE 25 / KES-USD live FX (not in database)
- Portfolio / Watchlist (phase 6)
- Calendar page (phase 5)
- Advanced screener filters (phase 3)
- Peer comparison tables (phase 4)
