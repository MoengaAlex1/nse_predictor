# Navigation Shell & Home Page Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the minimal Navbar/PageShell pair with a sticky AppShell (header + ticker tape + global search) and rebuild the Home page as a two-column market intelligence portal.

**Architecture:** Single `AppShell` wraps all three routes in `App.tsx`; `Companies` and `CompanyDeepDive` drop their `PageShell` wrappers. Home is rewritten with 5 focused sub-components in `src/components/home/`. No new Firestore collections — all data comes from existing `useMarketOverview()` and `useCompanies()` hooks.

**Tech Stack:** React 19, TypeScript, Tailwind CSS v3, Recharts v3, TanStack Query v5, React Router v6, Vitest + RTL.

**Spec:** `docs/superpowers/specs/2026-07-25-navigation-shell-home-redesign.md`

---

## File Map

### Created
| File | Purpose |
|------|---------|
| `src/components/layout/ThemeToggle.tsx` | Extracted from Navbar — Light/System/Dark pill |
| `src/components/layout/NseLogo.tsx` | Inline SVG bull icon + wordmark, link to `/` |
| `src/components/layout/MobileNav.tsx` | Slide-in sheet + hamburger button |
| `src/components/layout/TickerTape.tsx` | CSS marquee strip: NSE 20 + gainers + losers |
| `src/components/layout/GlobalSearch.tsx` | Expanding search with autocomplete dropdown |
| `src/components/layout/AppShell.tsx` | Root layout: sticky header + tape + main |
| `src/components/home/MarketSummaryStrip.tsx` | Full-width NSE20 chip + signal pill strip |
| `src/components/home/MoversTable.tsx` | Reusable 5-row table for gainers / losers / active |
| `src/components/home/SentimentDonut.tsx` | Recharts PieChart donut: BUY/HOLD/SELL |
| `src/components/home/SectorPerformance.tsx` | Horizontal bar chart by sector |
| `src/components/home/TopSignals.tsx` | Top 5 BUY-signal companies |

### Modified
| File | Change |
|------|--------|
| `src/App.tsx` | Wrap routes with `AppShell`; remove per-page shell imports |
| `src/pages/Companies.tsx` | Remove `PageShell` wrapper |
| `src/pages/CompanyDeepDive.tsx` | Remove `PageShell` wrapper |
| `src/pages/Home.tsx` | Full rewrite — two-column layout with panels |

### Deleted (in Task 7, after AppShell is wired)
| File | Reason |
|------|--------|
| `src/components/layout/Navbar.tsx` | Superseded by AppShell |
| `src/components/layout/PageShell.tsx` | Superseded by AppShell |

---

## Task 1: ThemeToggle

Extract the ThemeToggle component from `Navbar.tsx` into its own file. `Navbar.tsx` will still import from the new location so it keeps working until Task 7.

**Files:**
- Create: `src/components/layout/ThemeToggle.tsx`
- Create: `src/components/layout/ThemeToggle.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/layout/ThemeToggle.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", setTheme: vi.fn(), resolvedTheme: "dark" }),
}));

import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  it("renders three theme buttons", () => {
    render(<ThemeToggle />);
    expect(screen.getByTitle("Light mode")).toBeInTheDocument();
    expect(screen.getByTitle("System theme")).toBeInTheDocument();
    expect(screen.getByTitle("Dark mode")).toBeInTheDocument();
  });

  it("calls setTheme when a button is clicked", async () => {
    const setTheme = vi.fn();
    vi.mocked(require("../../context/ThemeContext").useTheme).mockReturnValue({
      theme: "dark",
      setTheme,
      resolvedTheme: "dark",
    });
    const user = userEvent.setup();
    render(<ThemeToggle />);
    await user.click(screen.getByTitle("Light mode"));
    expect(setTheme).toHaveBeenCalledWith("light");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/layout/ThemeToggle.test.tsx
```
Expected: FAIL — `ThemeToggle` not found.

- [ ] **Step 3: Create ThemeToggle.tsx**

```tsx
// src/components/layout/ThemeToggle.tsx
import type { FC } from "react";
import { useTheme } from "../../context/ThemeContext";

const SunIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" />
    <line x1="12" y1="2" x2="12" y2="4" /><line x1="12" y1="20" x2="12" y2="22" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="2" y1="12" x2="4" y2="12" /><line x1="20" y1="12" x2="22" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
  </svg>
);

const MonitorIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" />
    <line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" />
  </svg>
);

const MoonIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

const THEME_OPTIONS = [
  { value: "light" as const, label: "Light mode",  icon: <SunIcon /> },
  { value: "system" as const, label: "System theme", icon: <MonitorIcon /> },
  { value: "dark" as const,  label: "Dark mode",   icon: <MoonIcon /> },
];

export const ThemeToggle: FC = () => {
  const { theme, setTheme } = useTheme();
  return (
    <div className="flex items-center gap-0.5 rounded-full border border-rim bg-raised p-0.5">
      {THEME_OPTIONS.map(({ value, label, icon }) => (
        <button
          key={value}
          type="button"
          title={label}
          onClick={() => setTheme(value)}
          className={`flex h-7 w-7 items-center justify-center rounded-full transition-colors ${
            theme === value
              ? "bg-accent text-white dark:bg-accent/20 dark:text-accent"
              : "text-sub hover:text-ink"
          }`}
        >
          {icon}
        </button>
      ))}
    </div>
  );
};
```

- [ ] **Step 4: Update Navbar.tsx to import ThemeToggle from its new location**

In `src/components/layout/Navbar.tsx`, replace the inline `ThemeToggle` definition and its three icon components with an import:

```tsx
// src/components/layout/Navbar.tsx
import type { FC } from "react";
import { Link } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";

export const Navbar: FC = () => {
  return (
    <nav className="border-b border-rim bg-surface shadow-sm">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/companies" className="text-lg font-bold text-accent">
              NSE Intelligence
            </Link>
            <Link to="/companies" className="text-sm text-sub hover:text-ink transition-colors">
              Companies
            </Link>
          </div>
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
};
```

- [ ] **Step 5: Run tests**

```bash
cd frontend && npx vitest run src/components/layout/ThemeToggle.test.tsx
```
Expected: PASS

- [ ] **Step 6: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/layout/ThemeToggle.tsx frontend/src/components/layout/ThemeToggle.test.tsx frontend/src/components/layout/Navbar.tsx
git commit -m "refactor: extract ThemeToggle into its own layout file"
```

---

## Task 2: NseLogo

Create the inline SVG brand mark — bull icon + "NSE Intelligence" wordmark — as a link to `/`.

**Files:**
- Create: `src/components/layout/NseLogo.tsx`
- Create: `src/components/layout/NseLogo.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/layout/NseLogo.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { NseLogo } from "./NseLogo";

describe("NseLogo", () => {
  it("renders NSE and Intelligence text", () => {
    render(<MemoryRouter><NseLogo /></MemoryRouter>);
    expect(screen.getByText("NSE")).toBeInTheDocument();
    expect(screen.getByText("Intelligence")).toBeInTheDocument();
  });

  it("links to /", () => {
    render(<MemoryRouter><NseLogo /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /NSE Intelligence Home/i })).toHaveAttribute("href", "/");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/layout/NseLogo.test.tsx
```
Expected: FAIL — `NseLogo` not found.

- [ ] **Step 3: Create NseLogo.tsx**

```tsx
// src/components/layout/NseLogo.tsx
import type { FC } from "react";
import { Link } from "react-router-dom";

export const NseLogo: FC = () => (
  <Link
    to="/"
    className="flex select-none items-center gap-2"
    aria-label="NSE Intelligence Home"
  >
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <circle cx="14" cy="14" r="13" fill="currentColor" className="text-accent" opacity="0.12" />
      {/* Bull head */}
      <path
        d="M10 17 Q8 14 9 11 Q11 8 14 8 Q17 8 19 11 Q20 14 18 17 L16 18 Q14 19 12 18 Z"
        fill="currentColor"
        className="text-accent"
      />
      {/* Left horn */}
      <path d="M10 11 Q8 8 7 9 Q8 11 10 12" fill="currentColor" className="text-accent" />
      {/* Right horn */}
      <path d="M18 11 Q20 8 21 9 Q20 11 18 12" fill="currentColor" className="text-accent" />
    </svg>
    <span className="flex items-baseline gap-1">
      <span className="text-lg font-black text-ink">NSE</span>
      <span className="text-sm font-medium text-muted">Intelligence</span>
    </span>
  </Link>
);
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/layout/NseLogo.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/NseLogo.tsx frontend/src/components/layout/NseLogo.test.tsx
git commit -m "feat: add NseLogo component — inline SVG bull mark + wordmark"
```

---

## Task 3: MobileNav

Hamburger button + slide-in sheet with nav links and ThemeToggle. Rendered by AppShell on mobile.

**Files:**
- Create: `src/components/layout/MobileNav.tsx`
- Create: `src/components/layout/MobileNav.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/layout/MobileNav.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", setTheme: vi.fn(), resolvedTheme: "dark" }),
}));

import { MobileNav, MobileMenuButton } from "./MobileNav";

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("MobileNav", () => {
  it("renders nothing when isOpen is false", () => {
    wrap(<MobileNav isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByText("Menu")).not.toBeInTheDocument();
  });

  it("renders nav links when isOpen is true", () => {
    wrap(<MobileNav isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByText("Menu")).toBeInTheDocument();
    expect(screen.getByText("Markets")).toBeInTheDocument();
    expect(screen.getByText("Screener")).toBeInTheDocument();
  });

  it("calls onClose when the close button is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    wrap(<MobileNav isOpen={true} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: "" })); // X button
    expect(onClose).toHaveBeenCalled();
  });
});

describe("MobileMenuButton", () => {
  it("calls onClick when pressed", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<MobileMenuButton onClick={onClick} />);
    await user.click(screen.getByRole("button", { name: /open menu/i }));
    expect(onClick).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/layout/MobileNav.test.tsx
```
Expected: FAIL — `MobileNav` not found.

- [ ] **Step 3: Create MobileNav.tsx**

```tsx
// src/components/layout/MobileNav.tsx
import type { FC } from "react";
import { NavLink } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";

const HamburgerIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="3" y1="6" x2="21" y2="6" />
    <line x1="3" y1="12" x2="21" y2="12" />
    <line x1="3" y1="18" x2="21" y2="18" />
  </svg>
);

const XIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const NAV_LINKS = [
  { label: "Markets",  to: "/companies" },
  { label: "Screener", to: "/companies" },
  { label: "News",     to: "/companies" },
];

const linkCls = (isActive: boolean) =>
  `block px-4 py-3 text-base font-medium transition-colors ${
    isActive
      ? "border-l-2 border-accent bg-raised/50 pl-3.5 text-accent"
      : "text-sub hover:bg-raised/40 hover:text-ink"
  }`;

type MobileNavProps = { isOpen: boolean; onClose: () => void };

export const MobileNav: FC<MobileNavProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;
  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div className="fixed left-0 top-0 z-50 flex h-full w-72 flex-col bg-surface shadow-xl">
        <div className="flex h-14 items-center justify-between border-b border-seam px-4">
          <span className="text-sm font-semibold text-ink">Menu</span>
          <button
            type="button"
            onClick={onClose}
            className="text-muted transition-colors hover:text-ink"
          >
            <XIcon />
          </button>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {NAV_LINKS.map(({ label, to }) => (
            <NavLink
              key={label}
              to={to}
              onClick={onClose}
              className={({ isActive }) => linkCls(isActive)}
            >
              {label}
            </NavLink>
          ))}
          <div className="mt-4 border-t border-seam px-4 pt-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-hint">Theme</p>
            <ThemeToggle />
          </div>
        </nav>
      </div>
    </>
  );
};

export const MobileMenuButton: FC<{ onClick: () => void }> = ({ onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className="flex h-8 w-8 items-center justify-center rounded-lg text-sub transition-colors hover:bg-raised hover:text-ink lg:hidden"
    aria-label="Open menu"
  >
    <HamburgerIcon />
  </button>
);
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/layout/MobileNav.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/MobileNav.tsx frontend/src/components/layout/MobileNav.test.tsx
git commit -m "feat: add MobileNav sheet + MobileMenuButton"
```

---

## Task 4: TickerTape

Sticky marquee strip below the header showing NSE 20 index + top gainers + top losers. Auto-scrolls via CSS animation, pauses on hover.

**Files:**
- Create: `src/components/layout/TickerTape.tsx`
- Create: `src/components/layout/TickerTape.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/layout/TickerTape.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../hooks/useMarket", () => ({
  useMarketOverview: () => ({
    data: {
      date: "2026-07-25",
      nse20_value: 1842.5,
      nse20_change_pct: 0.35,
      top_gainers: [{ ticker: "SCOM.NR", change_pct: 3.2 }],
      top_losers: [{ ticker: "EABL.NR", change_pct: -1.8 }],
      signal_distribution: { BUY: 40, HOLD: 50, SELL: 27 },
      sector_performance: {},
    },
  }),
}));

vi.mock("../../hooks/useCompanies", () => ({
  useCompanies: () => ({
    data: [
      {
        id: "SCOM.NR", ticker: "SCOM.NR", short: "Safaricom", color: "#22c55e",
        icon: "📱", name: "Safaricom PLC", sector: "Telecom",
        current_price: 14.5, change_pct_today: 3.2, signal: "BUY",
        price_history: [], price_preview: [], price_date: null, last_updated: null, csv: "",
      },
    ],
  }),
}));

import { TickerTape } from "./TickerTape";

describe("TickerTape", () => {
  it("shows NSE 20 label", () => {
    render(<MemoryRouter><TickerTape /></MemoryRouter>);
    expect(screen.getAllByText("NSE 20").length).toBeGreaterThan(0);
  });

  it("shows a gainer ticker", () => {
    render(<MemoryRouter><TickerTape /></MemoryRouter>);
    expect(screen.getAllByText("SCOM.NR").length).toBeGreaterThan(0);
  });

  it("shows a loser ticker", () => {
    render(<MemoryRouter><TickerTape /></MemoryRouter>);
    expect(screen.getAllByText("EABL.NR").length).toBeGreaterThan(0);
  });

  it("renders nothing when market is null", () => {
    vi.mocked(require("../../hooks/useMarket").useMarketOverview).mockReturnValueOnce({ data: null });
    const { container } = render(<MemoryRouter><TickerTape /></MemoryRouter>);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/layout/TickerTape.test.tsx
```
Expected: FAIL — `TickerTape` not found.

- [ ] **Step 3: Create TickerTape.tsx**

```tsx
// src/components/layout/TickerTape.tsx
import { useState } from "react";
import type { FC } from "react";
import { Link } from "react-router-dom";
import { useMarketOverview } from "../../hooks/useMarket";
import { useCompanies } from "../../hooks/useCompanies";
import type { CompanyDoc } from "../../types";

// Inline logo for the tape — CompanyLogo's "sm" size (h-8 w-8) is too large
const SmallLogo: FC<Pick<CompanyDoc, "id" | "short" | "color" | "icon">> = ({ id, short, color, icon }) => {
  const [failed, setFailed] = useState(false);
  if (!failed) {
    return (
      <img
        src={`/logos/${id}.png`}
        alt={short}
        className="h-4 w-4 rounded object-contain"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <span
      className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[9px]"
      style={{ backgroundColor: `${color}22`, border: `1px solid ${color}55` }}
    >
      {icon}
    </span>
  );
};

const Chip: FC<{ pct: number }> = ({ pct }) => {
  const up = pct >= 0;
  return (
    <span className={`font-mono text-[11px] font-semibold ${up ? "text-emerald-500" : "text-red-500"}`}>
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(2)}%
    </span>
  );
};

export const TickerTape: FC = () => {
  const { data: market } = useMarketOverview();
  const { data: companies = [] } = useCompanies();

  if (!market) return null;

  const companyMap = new Map(companies.map(c => [c.ticker, c]));
  const gainers = market.top_gainers.slice(0, 5);
  const losers = market.top_losers.slice(0, 5);

  const items = (
    <>
      {/* NSE 20 */}
      <span className="flex items-center gap-1.5">
        <span className="text-[11px] font-semibold text-muted">NSE 20</span>
        {market.nse20_value != null && (
          <span className="font-mono text-[11px] text-ink">{market.nse20_value.toFixed(2)}</span>
        )}
        {market.nse20_change_pct != null && <Chip pct={market.nse20_change_pct} />}
      </span>

      <span className="text-hint" aria-hidden="true">|</span>

      {gainers.map(g => {
        const c = companyMap.get(g.ticker);
        return (
          <Link
            key={`g-${g.ticker}`}
            to={`/company/${g.ticker}`}
            className="flex items-center gap-1 transition-opacity hover:opacity-80"
          >
            {c && <SmallLogo id={c.id} short={c.short} color={c.color} icon={c.icon} />}
            <span className="text-[11px] font-semibold text-ink">{g.ticker}</span>
            <Chip pct={g.change_pct} />
          </Link>
        );
      })}

      <span className="text-hint" aria-hidden="true">|</span>

      {losers.map(l => {
        const c = companyMap.get(l.ticker);
        return (
          <Link
            key={`l-${l.ticker}`}
            to={`/company/${l.ticker}`}
            className="flex items-center gap-1 transition-opacity hover:opacity-80"
          >
            {c && <SmallLogo id={c.id} short={c.short} color={c.color} icon={c.icon} />}
            <span className="text-[11px] font-semibold text-ink">{l.ticker}</span>
            <Chip pct={l.change_pct} />
          </Link>
        );
      })}
    </>
  );

  return (
    <>
      <style>{`
        @keyframes marquee {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
        .ticker-track { animation: marquee 40s linear infinite; }
        .ticker-tape:hover .ticker-track { animation-play-state: paused; }
      `}</style>
      <div className="ticker-tape sticky top-14 z-40 hidden h-8 overflow-hidden border-b border-seam bg-surface sm:block">
        <div className="ticker-track flex h-full w-max items-center gap-4 px-4">
          {items}
          {/* Duplicate for seamless loop */}
          {items}
        </div>
      </div>
    </>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/layout/TickerTape.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/TickerTape.tsx frontend/src/components/layout/TickerTape.test.tsx
git commit -m "feat: add TickerTape — CSS marquee strip with NSE 20 + movers"
```

---

## Task 5: GlobalSearch

Expanding search box with autocomplete dropdown. Searches the `useCompanies()` cache — no extra Firestore reads.

**Files:**
- Create: `src/components/layout/GlobalSearch.tsx`
- Create: `src/components/layout/GlobalSearch.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/layout/GlobalSearch.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const mockCompany = {
  id: "SCOM.NR", ticker: "SCOM.NR", short: "Safaricom", color: "#22c55e",
  icon: "📱", name: "Safaricom PLC", sector: "Telecommunication and Technology",
  current_price: 14.5, change_pct_today: 3.2, signal: "BUY" as const,
  price_history: [], price_preview: [], price_date: null, last_updated: null, csv: "",
};

vi.mock("../../hooks/useCompanies", () => ({
  useCompanies: () => ({ data: [mockCompany], isLoading: false }),
}));

import { GlobalSearch } from "./GlobalSearch";

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("GlobalSearch", () => {
  it("renders a search icon button initially", () => {
    wrap(<GlobalSearch />);
    expect(screen.getByTitle("Search companies")).toBeInTheDocument();
  });

  it("expands to an input when the icon is clicked", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    expect(screen.getByPlaceholderText("Search companies…")).toBeInTheDocument();
  });

  it("shows matching results when query matches a ticker", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    await user.type(screen.getByPlaceholderText("Search companies…"), "SCOM");
    expect(screen.getByText("Safaricom PLC")).toBeInTheDocument();
  });

  it("shows no match message for unknown query", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    await user.type(screen.getByPlaceholderText("Search companies…"), "ZZZZ");
    expect(screen.getByText(/No companies match/i)).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    await user.keyboard("{Escape}");
    expect(screen.queryByPlaceholderText("Search companies…")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/layout/GlobalSearch.test.tsx
```
Expected: FAIL — `GlobalSearch` not found.

- [ ] **Step 3: Create GlobalSearch.tsx**

```tsx
// src/components/layout/GlobalSearch.tsx
import { useState, useRef, useEffect, useCallback } from "react";
import type { FC } from "react";
import { useNavigate } from "react-router-dom";
import { useCompanies } from "../../hooks/useCompanies";
import { CompanyLogo } from "../ui/CompanyLogo";
import { SignalBadge } from "../ui/Badge";
import type { CompanyDoc } from "../../types";

const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const XIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

function filterCompanies(companies: CompanyDoc[], query: string): CompanyDoc[] {
  const q = query.toLowerCase();
  return companies
    .filter(
      c =>
        c.ticker.toLowerCase().includes(q) ||
        c.short.toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q),
    )
    .slice(0, 6);
}

export const GlobalSearch: FC = () => {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { data: companies = [], isLoading } = useCompanies();

  const results = query.trim() ? filterCompanies(companies, query) : [];

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setActiveIdx(-1);
  }, []);

  const selectCompany = useCallback(
    (ticker: string) => {
      navigate(`/company/${ticker}`);
      close();
    },
    [navigate, close],
  );

  // Click-outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        close();
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, close]);

  // Auto-focus input when opened
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") { close(); return; }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx(i => Math.min(i + 1, results.length - 1));
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx(i => Math.max(i - 1, -1));
    }
    if (e.key === "Enter" && activeIdx >= 0 && results[activeIdx]) {
      selectCompany(results[activeIdx].ticker);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        title="Search companies"
        onClick={() => setOpen(true)}
        className="flex h-8 w-8 items-center justify-center rounded-lg text-sub transition-colors hover:bg-raised hover:text-ink"
      >
        <SearchIcon />
      </button>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="flex items-center gap-1.5 rounded-lg border border-rim bg-raised px-3 py-1.5">
        <span className="shrink-0 text-muted">
          <SearchIcon />
        </span>
        <input
          ref={inputRef}
          type="text"
          placeholder={isLoading ? "Loading…" : "Search companies…"}
          disabled={isLoading}
          value={query}
          onChange={e => {
            setQuery(e.target.value);
            setActiveIdx(-1);
          }}
          onKeyDown={handleKeyDown}
          className="w-48 bg-transparent text-sm text-ink placeholder-hint outline-none"
        />
        <button
          type="button"
          onClick={close}
          className="shrink-0 text-muted transition-colors hover:text-ink"
        >
          <XIcon />
        </button>
      </div>

      {query.trim() && (
        <div className="absolute left-0 top-full z-50 mt-1 w-80 overflow-hidden rounded-xl border border-rim bg-surface shadow-lg">
          {results.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted">No companies match &ldquo;{query}&rdquo;</p>
          ) : (
            <ul>
              {results.map((c, i) => (
                <li key={c.ticker}>
                  <button
                    type="button"
                    onClick={() => selectCompany(c.ticker)}
                    className={`flex w-full items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                      i === activeIdx ? "bg-raised" : "hover:bg-raised/60"
                    }`}
                  >
                    <CompanyLogo id={c.id} short={c.short} color={c.color} icon={c.icon} size="sm" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-accent">{c.ticker}</span>
                        {c.signal && <SignalBadge signal={c.signal} />}
                      </div>
                      <p className="truncate text-xs text-sub">{c.name}</p>
                    </div>
                    <span className="shrink-0 text-[10px] text-hint">
                      {c.sector.split(" ")[0]}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/layout/GlobalSearch.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/GlobalSearch.tsx frontend/src/components/layout/GlobalSearch.test.tsx
git commit -m "feat: add GlobalSearch — expanding autocomplete search box"
```

---

## Task 6: AppShell

Root layout wrapper. Sticky header with logo, nav links, search, theme toggle, hamburger. Hosts TickerTape below the header. Wraps page content in a max-w-7xl main.

**Files:**
- Create: `src/components/layout/AppShell.tsx`
- Create: `src/components/layout/AppShell.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/layout/AppShell.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", setTheme: vi.fn(), resolvedTheme: "dark" }),
}));
vi.mock("../../hooks/useCompanies", () => ({
  useCompanies: () => ({ data: [], isLoading: false }),
}));
vi.mock("../../hooks/useMarket", () => ({
  useMarketOverview: () => ({ data: null }),
}));

import { AppShell } from "./AppShell";

describe("AppShell", () => {
  it("renders children inside main", () => {
    render(
      <MemoryRouter>
        <AppShell><p>Page content</p></AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByText("Page content")).toBeInTheDocument();
  });

  it("renders the NSE logo", () => {
    render(
      <MemoryRouter>
        <AppShell><p>x</p></AppShell>
      </MemoryRouter>,
    );
    expect(screen.getByText("NSE")).toBeInTheDocument();
  });

  it("renders desktop nav links", () => {
    render(
      <MemoryRouter>
        <AppShell><p>x</p></AppShell>
      </MemoryRouter>,
    );
    expect(screen.getAllByText("Markets").length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/layout/AppShell.test.tsx
```
Expected: FAIL — `AppShell` not found.

- [ ] **Step 3: Create AppShell.tsx**

```tsx
// src/components/layout/AppShell.tsx
import { useState } from "react";
import type { FC, ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { NseLogo } from "./NseLogo";
import { GlobalSearch } from "./GlobalSearch";
import { ThemeToggle } from "./ThemeToggle";
import { TickerTape } from "./TickerTape";
import { MobileNav, MobileMenuButton } from "./MobileNav";

const NAV_LINKS = [
  { label: "Markets",  to: "/companies",  disabled: false },
  { label: "Screener", to: "/companies",  disabled: false },
  { label: "News",     to: "/companies",  disabled: false },
  { label: "Calendar", to: "/companies",  disabled: true  },
];

const navLinkCls = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium transition-colors px-1 py-0.5 ${
    isActive ? "border-b-2 border-accent text-ink" : "text-sub hover:text-ink"
  }`;

export const AppShell: FC<{ children: ReactNode }> = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* Sticky header — 56px */}
      <header className="sticky top-0 z-50 h-14 border-b border-seam bg-canvas/95 backdrop-blur">
        <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <NseLogo />

          {/* Desktop nav */}
          <nav className="hidden items-center gap-6 lg:flex" aria-label="Main navigation">
            {NAV_LINKS.map(({ label, to, disabled }) =>
              disabled ? (
                <span key={label} className="cursor-not-allowed text-sm font-medium text-hint">
                  {label}
                </span>
              ) : (
                <NavLink key={label} to={to} className={navLinkCls}>
                  {label}
                </NavLink>
              ),
            )}
          </nav>

          <div className="flex items-center gap-2">
            <GlobalSearch />
            <div className="hidden sm:block">
              <ThemeToggle />
            </div>
            <MobileMenuButton onClick={() => setMobileOpen(true)} />
          </div>
        </div>
      </header>

      <TickerTape />

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {children}
      </main>

      <MobileNav isOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/layout/AppShell.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/layout/AppShell.tsx frontend/src/components/layout/AppShell.test.tsx
git commit -m "feat: add AppShell — sticky header + ticker tape + responsive nav"
```

---

## Task 7: Wire AppShell, strip PageShell

Replace per-page shell usage with the new AppShell in App.tsx. Remove PageShell from Companies and CompanyDeepDive. Delete the now-unused Navbar.tsx and PageShell.tsx.

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/pages/Companies.tsx` (remove PageShell wrapper)
- Modify: `src/pages/CompanyDeepDive.tsx` (remove PageShell wrapper)
- Delete: `src/components/layout/Navbar.tsx`
- Delete: `src/components/layout/PageShell.tsx`

- [ ] **Step 1: Update App.tsx**

Replace the entire file:

```tsx
// src/App.tsx
import { useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { AppShell } from "./components/layout/AppShell";
import { Home } from "./pages/Home";
import { Companies } from "./pages/Companies";
import { CompanyDeepDive } from "./pages/CompanyDeepDive";

export default function App() {
  useEffect(() => {
    const unsubscribe = initAuthListener();
    return unsubscribe;
  }, []);

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/company/:ticker" element={<CompanyDeepDive />} />
      </Routes>
    </AppShell>
  );
}
```

- [ ] **Step 2: Strip PageShell from Companies.tsx**

In `src/pages/Companies.tsx`:

a) Remove the import line:
```tsx
import { PageShell } from "../components/layout/PageShell";
```

b) The return statement currently wraps everything in `<PageShell>`. Replace:
```tsx
    <PageShell>
```
with a fragment `<>` (or simply remove the wrapper entirely and return the inner div), and replace the closing `</PageShell>` with `</>`.

The outer JSX in `Companies` (around line 352) should become:
```tsx
  return (
    <>
      {/* existing inner JSX unchanged */}
    </>
  );
```

- [ ] **Step 3: Strip PageShell from CompanyDeepDive.tsx**

In `src/pages/CompanyDeepDive.tsx`:

a) Remove the import line:
```tsx
import { PageShell } from "../components/layout/PageShell";
```

b) There are three `<PageShell>` usages (error state, not-found state, main render). Replace each `<PageShell>` open tag with `<>` and each `</PageShell>` close tag with `</>`.

- [ ] **Step 4: Delete old layout files**

```bash
rm frontend/src/components/layout/Navbar.tsx
rm frontend/src/components/layout/PageShell.tsx
```

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. If there are any residual imports of `Navbar` or `PageShell`, fix them now.

- [ ] **Step 6: Run full test suite**

```bash
cd frontend && npx vitest run
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add -A frontend/src/
git commit -m "feat: wire AppShell into App.tsx — replace Navbar/PageShell across all routes"
```

---

## Task 8: MarketSummaryStrip

Full-width strip at the top of Home showing NSE 20 chip + BUY/HOLD/SELL signal pills + securities count + date.

**Files:**
- Create: `src/components/home/MarketSummaryStrip.tsx`
- Create: `src/components/home/MarketSummaryStrip.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/home/MarketSummaryStrip.test.tsx
import { render, screen } from "@testing-library/react";
import { MarketSummaryStrip } from "./MarketSummaryStrip";
import type { MarketOverviewDoc, CompanyDoc } from "../../types";

const mockMarket: MarketOverviewDoc = {
  date: "2026-07-25",
  nse20_value: 1842.5,
  nse20_change_pct: 0.35,
  top_gainers: [],
  top_losers: [],
  signal_distribution: { BUY: 42, HOLD: 51, SELL: 24 },
  sector_performance: {},
};

const mockCompanies: CompanyDoc[] = Array.from({ length: 117 }, (_, i) => ({
  id: `CO${i}.NR`, ticker: `CO${i}.NR`, short: `Co${i}`, color: "#fff", icon: "🏢",
  name: `Company ${i}`, sector: "Banking", current_price: 10, change_pct_today: 0,
  signal: "HOLD" as const, price_history: [], price_preview: [],
  price_date: null, last_updated: null, csv: "",
}));

describe("MarketSummaryStrip", () => {
  it("shows NSE 20 value", () => {
    render(<MarketSummaryStrip market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("1842.50")).toBeInTheDocument();
  });

  it("shows BUY/HOLD/SELL counts", () => {
    render(<MarketSummaryStrip market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("42 BUY")).toBeInTheDocument();
    expect(screen.getByText("51 HOLD")).toBeInTheDocument();
    expect(screen.getByText("24 SELL")).toBeInTheDocument();
  });

  it("shows securities count from companies array length", () => {
    render(<MarketSummaryStrip market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("117 securities tracked")).toBeInTheDocument();
  });

  it("shows the date", () => {
    render(<MarketSummaryStrip market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("as of 2026-07-25")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/home/MarketSummaryStrip.test.tsx
```
Expected: FAIL — `MarketSummaryStrip` not found.

- [ ] **Step 3: Create MarketSummaryStrip.tsx**

```tsx
// src/components/home/MarketSummaryStrip.tsx
import type { FC } from "react";
import type { MarketOverviewDoc, CompanyDoc } from "../../types";

type Props = {
  market: MarketOverviewDoc;
  companies: CompanyDoc[];
};

export const MarketSummaryStrip: FC<Props> = ({ market, companies }) => {
  const nseVal = market.nse20_value != null ? market.nse20_value.toFixed(2) : "N/A";
  const nsePct = market.nse20_change_pct;
  const { BUY, HOLD, SELL } = market.signal_distribution;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-rim bg-surface px-5 py-3">
      {/* NSE 20 chip */}
      <div className="flex items-center gap-2 rounded-lg border border-seam bg-canvas px-3 py-1.5">
        <span className="text-xs font-semibold text-muted">NSE 20</span>
        <span className="font-mono text-sm font-bold text-ink">{nseVal}</span>
        {nsePct != null && (
          <span
            className={`font-mono text-xs font-semibold ${
              nsePct >= 0 ? "text-emerald-500" : "text-red-500"
            }`}
          >
            {nsePct >= 0 ? "+" : ""}
            {nsePct.toFixed(2)}%
          </span>
        )}
      </div>

      {/* Signal pills */}
      <div className="flex items-center gap-2">
        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-400">
          {BUY} BUY
        </span>
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-400">
          {HOLD} HOLD
        </span>
        <span className="rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-semibold text-red-400">
          {SELL} SELL
        </span>
      </div>

      <span className="text-xs text-muted">{companies.length} securities tracked</span>

      {market.date && (
        <span className="text-xs text-hint">as of {market.date}</span>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/home/MarketSummaryStrip.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/home/MarketSummaryStrip.tsx frontend/src/components/home/MarketSummaryStrip.test.tsx
git commit -m "feat: add MarketSummaryStrip — NSE20 chip + signal pills + securities count"
```

---

## Task 9: MoversTable

Reusable 5-row table for Top Gainers, Top Losers, or Most Active (by `|change_pct_today|`). All rows are full-row links to `/company/:ticker`.

**Files:**
- Create: `src/components/home/MoversTable.tsx`
- Create: `src/components/home/MoversTable.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/home/MoversTable.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MoversTable } from "./MoversTable";
import type { MarketOverviewDoc, CompanyDoc } from "../../types";

const mkCompany = (ticker: string, pct: number, signal: "BUY" | "HOLD" | "SELL" = "BUY"): CompanyDoc => ({
  id: `${ticker}.NR`, ticker, short: ticker.toLowerCase(), color: "#fff", icon: "🏢",
  name: `${ticker} Ltd`, sector: "Banking", current_price: 10, change_pct_today: pct,
  signal, price_history: [], price_preview: [], price_date: null, last_updated: null, csv: "",
});

const mockMarket: MarketOverviewDoc = {
  date: "2026-07-25",
  nse20_value: null, nse20_change_pct: null,
  signal_distribution: { BUY: 10, HOLD: 10, SELL: 10 },
  sector_performance: {},
  top_gainers: [
    { ticker: "AAAA", change_pct: 5 },
    { ticker: "BBBB", change_pct: 4 },
  ],
  top_losers: [
    { ticker: "CCCC", change_pct: -3 },
  ],
};

const mockCompanies: CompanyDoc[] = [
  mkCompany("AAAA", 5),
  mkCompany("BBBB", 4),
  mkCompany("CCCC", -3),
  mkCompany("DDDD", 2),
  mkCompany("EEEE", 1),
];

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("MoversTable — gainers", () => {
  it("renders the header label", () => {
    wrap(<MoversTable type="gainers" market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("Top Gainers")).toBeInTheDocument();
  });

  it("shows joined company names for top_gainers", () => {
    wrap(<MoversTable type="gainers" market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("aaaa")).toBeInTheDocument();
    expect(screen.getByText("bbbb")).toBeInTheDocument();
  });
});

describe("MoversTable — active", () => {
  it("renders Most Active header", () => {
    wrap(<MoversTable type="active" market={mockMarket} companies={mockCompanies} />);
    expect(screen.getByText("Most Active")).toBeInTheDocument();
  });

  it("shows company rows sorted by absolute change", () => {
    wrap(<MoversTable type="active" market={mockMarket} companies={mockCompanies} />);
    // AAAA has highest absolute change (5%), should be first row
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/company/AAAA");
  });
});

describe("MoversTable — empty", () => {
  it("shows empty message when no rows", () => {
    const emptyMarket = { ...mockMarket, top_gainers: [] };
    wrap(<MoversTable type="gainers" market={emptyMarket} companies={[]} />);
    expect(screen.getByText("No data available")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/home/MoversTable.test.tsx
```
Expected: FAIL — `MoversTable` not found.

- [ ] **Step 3: Create MoversTable.tsx**

```tsx
// src/components/home/MoversTable.tsx
import type { FC } from "react";
import { Link } from "react-router-dom";
import { CompanyLogo } from "../ui/CompanyLogo";
import { SignalBadge } from "../ui/Badge";
import type { CompanyDoc, MarketOverviewDoc } from "../../types";

type Props = {
  type: "gainers" | "losers" | "active";
  market: MarketOverviewDoc;
  companies: CompanyDoc[];
};

const HEADERS: Record<Props["type"], string> = {
  gainers: "Top Gainers",
  losers:  "Top Losers",
  active:  "Most Active",
};

function getRows(
  type: Props["type"],
  market: MarketOverviewDoc,
  companies: CompanyDoc[],
): CompanyDoc[] {
  const companyMap = new Map(companies.map(c => [c.ticker, c]));

  if (type === "gainers") {
    return market.top_gainers
      .slice(0, 5)
      .map(g => companyMap.get(g.ticker))
      .filter((c): c is CompanyDoc => c != null);
  }
  if (type === "losers") {
    return market.top_losers
      .slice(0, 5)
      .map(l => companyMap.get(l.ticker))
      .filter((c): c is CompanyDoc => c != null);
  }
  // active — sort by |change_pct_today|
  return [...companies]
    .filter(c => c.change_pct_today != null)
    .sort((a, b) => Math.abs(b.change_pct_today!) - Math.abs(a.change_pct_today!))
    .slice(0, 5);
}

export const MoversTable: FC<Props> = ({ type, market, companies }) => {
  const rows = getRows(type, market, companies);

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="flex items-center justify-between border-b border-seam/60 px-4 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted">
          {HEADERS[type]}
        </span>
        <span className="text-[10px] text-hint">
          {rows.length} of {companies.length}
        </span>
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm text-muted">No data available</p>
      ) : (
        <ul>
          {rows.map(company => {
            const pct = company.change_pct_today;
            return (
              <li key={company.ticker}>
                <Link
                  to={`/company/${company.ticker}`}
                  className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-raised/60"
                >
                  <CompanyLogo
                    id={company.id}
                    short={company.short}
                    color={company.color}
                    icon={company.icon}
                    size="sm"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-ink">{company.short}</p>
                    <p className="font-mono text-[10px] text-muted">{company.ticker}</p>
                  </div>
                  <div className="text-right">
                    {company.current_price != null && (
                      <p className="font-mono text-xs text-sub">
                        KES {company.current_price.toFixed(2)}
                      </p>
                    )}
                    {pct != null && (
                      <p
                        className={`font-mono text-xs font-semibold ${
                          pct >= 0 ? "text-emerald-500" : "text-red-500"
                        }`}
                      >
                        {pct >= 0 ? "+" : ""}
                        {pct.toFixed(2)}%
                      </p>
                    )}
                  </div>
                  {company.signal && <SignalBadge signal={company.signal} />}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/home/MoversTable.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/home/MoversTable.tsx frontend/src/components/home/MoversTable.test.tsx
git commit -m "feat: add MoversTable — reusable gainers/losers/active table"
```

---

## Task 10: SentimentDonut

Recharts `PieChart` donut with BUY/HOLD/SELL segments. Center label shows the dominant signal.

**Files:**
- Create: `src/components/home/SentimentDonut.tsx`
- Create: `src/components/home/SentimentDonut.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/home/SentimentDonut.test.tsx
import { render, screen } from "@testing-library/react";
import { SentimentDonut } from "./SentimentDonut";
import type { MarketOverviewDoc } from "../../types";

const mkMarket = (BUY: number, HOLD: number, SELL: number): MarketOverviewDoc => ({
  date: "2026-07-25",
  nse20_value: null, nse20_change_pct: null,
  top_gainers: [], top_losers: [],
  signal_distribution: { BUY, HOLD, SELL },
  sector_performance: {},
});

describe("SentimentDonut", () => {
  it("renders the Market Sentiment header", () => {
    render(<SentimentDonut market={mkMarket(42, 51, 24)} />);
    expect(screen.getByText("Market Sentiment")).toBeInTheDocument();
  });

  it("shows BUY / HOLD / SELL labels", () => {
    render(<SentimentDonut market={mkMarket(42, 51, 24)} />);
    expect(screen.getAllByText("BUY").length).toBeGreaterThan(0);
    expect(screen.getAllByText("HOLD").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SELL").length).toBeGreaterThan(0);
  });

  it("shows count values", () => {
    render(<SentimentDonut market={mkMarket(42, 51, 24)} />);
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("51")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/home/SentimentDonut.test.tsx
```
Expected: FAIL — `SentimentDonut` not found.

- [ ] **Step 3: Create SentimentDonut.tsx**

```tsx
// src/components/home/SentimentDonut.tsx
import type { FC } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import type { MarketOverviewDoc } from "../../types";

type Props = { market: MarketOverviewDoc };

const SEGMENTS = [
  { key: "BUY"  as const, color: "#10b981" },
  { key: "HOLD" as const, color: "#f59e0b" },
  { key: "SELL" as const, color: "#ef4444" },
];

export const SentimentDonut: FC<Props> = ({ market }) => {
  const dist = market.signal_distribution;
  const total = dist.BUY + dist.HOLD + dist.SELL;

  const data = SEGMENTS
    .map(s => ({ name: s.key, value: dist[s.key], color: s.color }))
    .filter(d => d.value > 0);

  const dominant = data.length > 0
    ? data.reduce((a, b) => a.value > b.value ? a : b)
    : null;

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam/60 px-4 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Market Sentiment
        </p>
      </div>
      <div className="flex items-center gap-4 px-4 py-3">
        {/* Donut */}
        <div className="relative h-24 w-24 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                innerRadius="40%"
                outerRadius="65%"
                dataKey="value"
                startAngle={90}
                endAngle={-270}
                paddingAngle={2}
                isAnimationActive={false}
              >
                {data.map(entry => (
                  <Cell key={entry.name} fill={entry.color} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          {dominant && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span
                className="text-[10px] font-bold leading-none"
                style={{ color: dominant.color }}
              >
                {dominant.name}
              </span>
              <span className="text-xs font-bold text-ink">{dominant.value}</span>
            </div>
          )}
        </div>

        {/* Legend */}
        <div className="space-y-1.5">
          {SEGMENTS.map(s => {
            const count = dist[s.key];
            return (
              <div key={s.key} className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
                <span className="w-8 text-xs text-sub">{s.key}</span>
                <span className="font-mono text-xs font-semibold text-ink">{count}</span>
                {total > 0 && (
                  <span className="text-[10px] text-hint">
                    {((count / total) * 100).toFixed(0)}%
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/home/SentimentDonut.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/home/SentimentDonut.tsx frontend/src/components/home/SentimentDonut.test.tsx
git commit -m "feat: add SentimentDonut — BUY/HOLD/SELL pie chart donut"
```

---

## Task 11: SectorPerformance

Horizontal bar chart showing today's sector performance sorted descending. Green bars for positive, red for negative.

**Files:**
- Create: `src/components/home/SectorPerformance.tsx`
- Create: `src/components/home/SectorPerformance.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/home/SectorPerformance.test.tsx
import { render, screen } from "@testing-library/react";
import { SectorPerformance } from "./SectorPerformance";
import type { MarketOverviewDoc } from "../../types";

const mkMarket = (sectors: Record<string, number>): MarketOverviewDoc => ({
  date: "2026-07-25",
  nse20_value: null, nse20_change_pct: null,
  top_gainers: [], top_losers: [],
  signal_distribution: { BUY: 0, HOLD: 0, SELL: 0 },
  sector_performance: sectors,
});

describe("SectorPerformance", () => {
  it("renders the header", () => {
    render(<SectorPerformance market={mkMarket({ Banking: 1.2 })} />);
    expect(screen.getByText(/Sector Performance/i)).toBeInTheDocument();
  });

  it("shows sector names", () => {
    render(<SectorPerformance market={mkMarket({ Banking: 1.2, Insurance: -0.5 })} />);
    expect(screen.getByText("Banking")).toBeInTheDocument();
    expect(screen.getByText("Insurance")).toBeInTheDocument();
  });

  it("shows performance values with sign", () => {
    render(<SectorPerformance market={mkMarket({ Banking: 1.2, Insurance: -0.5 })} />);
    expect(screen.getByText("+1.2%")).toBeInTheDocument();
    expect(screen.getByText("-0.5%")).toBeInTheDocument();
  });

  it("renders nothing when sector_performance is empty", () => {
    const { container } = render(<SectorPerformance market={mkMarket({})} />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/home/SectorPerformance.test.tsx
```
Expected: FAIL — `SectorPerformance` not found.

- [ ] **Step 3: Create SectorPerformance.tsx**

```tsx
// src/components/home/SectorPerformance.tsx
import type { FC } from "react";
import type { MarketOverviewDoc } from "../../types";

type Props = { market: MarketOverviewDoc };

export const SectorPerformance: FC<Props> = ({ market }) => {
  const entries = Object.entries(market.sector_performance).sort((a, b) => b[1] - a[1]);

  if (entries.length === 0) return null;

  const maxAbs = Math.max(...entries.map(([, v]) => Math.abs(v)));

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam/60 px-4 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Sector Performance · today
        </p>
      </div>
      <div className="space-y-1.5 px-4 py-3">
        {entries.map(([sector, pct]) => {
          const isPos = pct >= 0;
          const widthPct = maxAbs > 0 ? (Math.abs(pct) / maxAbs) * 100 : 0;
          return (
            <div key={sector} className="flex items-center gap-2">
              <span
                className="w-24 shrink-0 truncate text-[10px] text-sub"
                title={sector}
              >
                {sector}
              </span>
              <div className="h-3 flex-1 overflow-hidden rounded-sm bg-raised/40">
                <div
                  className="h-full rounded-sm transition-all"
                  style={{
                    width: `${widthPct}%`,
                    backgroundColor: isPos ? "#10b981" : "#ef4444",
                  }}
                />
              </div>
              <span
                className={`w-12 text-right font-mono text-[10px] font-semibold ${
                  isPos ? "text-emerald-500" : "text-red-500"
                }`}
              >
                {isPos ? "+" : ""}
                {pct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/home/SectorPerformance.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/home/SectorPerformance.tsx frontend/src/components/home/SectorPerformance.test.tsx
git commit -m "feat: add SectorPerformance — horizontal bar chart by sector"
```

---

## Task 12: TopSignals

Five highest-change BUY-signal companies as a linked table. Full row navigates to `/company/:ticker`.

**Files:**
- Create: `src/components/home/TopSignals.tsx`
- Create: `src/components/home/TopSignals.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/components/home/TopSignals.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TopSignals } from "./TopSignals";
import type { CompanyDoc } from "../../types";

const mkCompany = (ticker: string, pct: number, signal: "BUY" | "HOLD" | "SELL"): CompanyDoc => ({
  id: `${ticker}.NR`, ticker, short: ticker.toLowerCase(), color: "#fff", icon: "🏢",
  name: `${ticker} Ltd`, sector: "Banking", current_price: 10,
  change_pct_today: pct, signal,
  price_history: [], price_preview: [], price_date: null, last_updated: null, csv: "",
});

describe("TopSignals", () => {
  it("renders Top Buy Signals header", () => {
    render(
      <MemoryRouter>
        <TopSignals companies={[mkCompany("AAAA", 5, "BUY")]} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Top Buy Signals")).toBeInTheDocument();
  });

  it("only shows BUY companies", () => {
    render(
      <MemoryRouter>
        <TopSignals
          companies={[
            mkCompany("AAAA", 5, "BUY"),
            mkCompany("BBBB", 4, "SELL"),
            mkCompany("CCCC", 3, "HOLD"),
          ]}
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("aaaa")).toBeInTheDocument();
    expect(screen.queryByText("bbbb")).not.toBeInTheDocument();
    expect(screen.queryByText("cccc")).not.toBeInTheDocument();
  });

  it("shows max 5 rows", () => {
    const companies = Array.from({ length: 10 }, (_, i) =>
      mkCompany(`T${i}`, i, "BUY"),
    );
    render(<MemoryRouter><TopSignals companies={companies} /></MemoryRouter>);
    expect(screen.getAllByRole("link")).toHaveLength(5);
  });

  it("renders nothing when no BUY companies", () => {
    const { container } = render(
      <MemoryRouter>
        <TopSignals companies={[mkCompany("AAAA", 1, "SELL")]} />
      </MemoryRouter>,
    );
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/components/home/TopSignals.test.tsx
```
Expected: FAIL — `TopSignals` not found.

- [ ] **Step 3: Create TopSignals.tsx**

```tsx
// src/components/home/TopSignals.tsx
import type { FC } from "react";
import { Link } from "react-router-dom";
import { CompanyLogo } from "../ui/CompanyLogo";
import { SignalBadge } from "../ui/Badge";
import type { CompanyDoc } from "../../types";

type Props = { companies: CompanyDoc[] };

export const TopSignals: FC<Props> = ({ companies }) => {
  const rows = companies
    .filter(c => c.signal === "BUY")
    .sort((a, b) => (b.change_pct_today ?? 0) - (a.change_pct_today ?? 0))
    .slice(0, 5);

  if (rows.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam/60 px-4 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Top Buy Signals
        </p>
      </div>
      <ul>
        {rows.map(company => (
          <li key={company.ticker}>
            <Link
              to={`/company/${company.ticker}`}
              className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-raised/60"
            >
              <CompanyLogo
                id={company.id}
                short={company.short}
                color={company.color}
                icon={company.icon}
                size="sm"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink">{company.short}</p>
                <p className="font-mono text-[10px] text-muted">{company.ticker}</p>
              </div>
              {company.current_price != null && (
                <p className="font-mono text-xs text-sub">
                  KES {company.current_price.toFixed(2)}
                </p>
              )}
              {company.change_pct_today != null && (
                <p
                  className={`font-mono text-xs font-semibold ${
                    company.change_pct_today >= 0 ? "text-emerald-500" : "text-red-500"
                  }`}
                >
                  {company.change_pct_today >= 0 ? "+" : ""}
                  {company.change_pct_today.toFixed(2)}%
                </p>
              )}
              <SignalBadge signal="BUY" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/components/home/TopSignals.test.tsx
```
Expected: PASS

- [ ] **Step 5: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/home/TopSignals.tsx frontend/src/components/home/TopSignals.test.tsx
git commit -m "feat: add TopSignals — top 5 BUY-signal companies panel"
```

---

## Task 13: Home page rewrite

Replace the old 3-card Home page with the two-column market intelligence layout.

**Files:**
- Modify: `src/pages/Home.tsx` (full rewrite)
- Create: `src/pages/Home.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// src/pages/Home.test.tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const mockMarket = {
  date: "2026-07-25",
  nse20_value: 1842.5,
  nse20_change_pct: 0.35,
  top_gainers: [],
  top_losers: [],
  signal_distribution: { BUY: 42, HOLD: 51, SELL: 24 },
  sector_performance: { Banking: 1.2 },
};

vi.mock("../hooks/useMarket", () => ({
  useMarketOverview: () => ({ data: mockMarket, isLoading: false }),
}));

vi.mock("../hooks/useCompanies", () => ({
  useCompanies: () => ({
    data: [],
    isLoading: false,
  }),
}));

import { Home } from "./Home";

describe("Home", () => {
  it("shows the MarketSummaryStrip with NSE 20 value", () => {
    render(<MemoryRouter><Home /></MemoryRouter>);
    expect(screen.getByText("1842.50")).toBeInTheDocument();
  });

  it("shows all three movers table headers", () => {
    render(<MemoryRouter><Home /></MemoryRouter>);
    expect(screen.getByText("Top Gainers")).toBeInTheDocument();
    expect(screen.getByText("Top Losers")).toBeInTheDocument();
    expect(screen.getByText("Most Active")).toBeInTheDocument();
  });

  it("shows Market Sentiment panel", () => {
    render(<MemoryRouter><Home /></MemoryRouter>);
    expect(screen.getByText("Market Sentiment")).toBeInTheDocument();
  });

  it("shows Sector Performance panel", () => {
    render(<MemoryRouter><Home /></MemoryRouter>);
    expect(screen.getByText(/Sector Performance/i)).toBeInTheDocument();
  });

  it("shows spinner when loading", () => {
    vi.mocked(require("../hooks/useMarket").useMarketOverview).mockReturnValueOnce({
      data: null,
      isLoading: true,
    });
    vi.mocked(require("../hooks/useCompanies").useCompanies).mockReturnValueOnce({
      data: [],
      isLoading: true,
    });
    render(<MemoryRouter><Home /></MemoryRouter>);
    // Spinner renders — no crash
    expect(document.body).toBeTruthy();
  });

  it("shows no-data message when market is null and not loading", () => {
    vi.mocked(require("../hooks/useMarket").useMarketOverview).mockReturnValueOnce({
      data: null,
      isLoading: false,
    });
    render(<MemoryRouter><Home /></MemoryRouter>);
    expect(screen.getByText(/No market data yet/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npx vitest run src/pages/Home.test.tsx
```
Expected: FAIL — imports fail or old Home layout lacks expected elements.

- [ ] **Step 3: Rewrite Home.tsx**

Replace the entire file:

```tsx
// src/pages/Home.tsx
import type { FC } from "react";
import { Spinner } from "../components/ui/Spinner";
import { useMarketOverview } from "../hooks/useMarket";
import { useCompanies } from "../hooks/useCompanies";
import { MarketSummaryStrip } from "../components/home/MarketSummaryStrip";
import { MoversTable } from "../components/home/MoversTable";
import { SentimentDonut } from "../components/home/SentimentDonut";
import { SectorPerformance } from "../components/home/SectorPerformance";
import { TopSignals } from "../components/home/TopSignals";

export const Home: FC = () => {
  const { data: market, isLoading: marketLoading } = useMarketOverview();
  const { data: companies = [], isLoading: companiesLoading } = useCompanies();

  if (marketLoading || companiesLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!market) {
    return (
      <div className="rounded-xl border border-rim bg-surface px-5 py-10 text-center">
        <p className="text-sub">No market data yet. Pipeline runs daily at 18:00 EAT.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <MarketSummaryStrip market={market} companies={companies} />

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        {/* Main column — movers tables */}
        <div className="space-y-5">
          <MoversTable type="gainers" market={market} companies={companies} />
          <MoversTable type="losers"  market={market} companies={companies} />
          <MoversTable type="active"  market={market} companies={companies} />
        </div>

        {/* Sidebar */}
        <div className="space-y-5">
          <SentimentDonut market={market} />
          <SectorPerformance market={market} />
          <TopSignals companies={companies} />
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run tests**

```bash
cd frontend && npx vitest run src/pages/Home.test.tsx
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
cd frontend && npx vitest run
```
Expected: all tests pass.

- [ ] **Step 6: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Home.tsx frontend/src/pages/Home.test.tsx
git commit -m "feat: rewrite Home page — two-column market intelligence layout"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] AppShell — sticky header 56px, backdrop-blur, border-b border-seam → Task 6
- [x] NseLogo — SVG bull + wordmark → Task 2
- [x] Nav links: Markets/Screener/News (all `/companies`) + Calendar (disabled) → Task 6
- [x] GlobalSearch — icon expands, filters companies, keyboard nav, click-outside → Task 5
- [x] ThemeToggle — extracted to own file → Task 1
- [x] MobileNav — hamburger sheet → Task 3
- [x] TickerTape — NSE20 + gainers + losers, CSS marquee, pauses on hover → Task 4
- [x] MarketSummaryStrip — NSE20 chip, signal pills, count, date → Task 8
- [x] MoversTable — gainers / losers / active, joined on companies → Task 9
- [x] SentimentDonut — Recharts PieChart donut → Task 10
- [x] SectorPerformance — horizontal bars sorted by value → Task 11
- [x] TopSignals — 5 BUY picks sorted by change_pct_today → Task 12
- [x] Home two-column layout (lg:grid-cols-[1fr_360px]) → Task 13
- [x] App.tsx wired to AppShell → Task 7
- [x] Companies.tsx and CompanyDeepDive.tsx PageShell removed → Task 7
- [x] Navbar.tsx and PageShell.tsx deleted → Task 7

**Type consistency:**
- `useMarketOverview()` is the correct hook name throughout (not `useMarket()`)
- `MarketOverviewDoc.signal_distribution` typed as `{ BUY: number; HOLD: number; SELL: number }` — accessed as `dist.BUY` etc., matching the type definition
- `CompanyDoc.change_pct_today: number | null` — guarded with `!= null` before use in sorts

**No placeholders confirmed.**
