import { useState, useEffect, useCallback } from "react";
import type { FC, ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { NseLogo } from "../components/layout/NseLogo";
import { GlobalSearch } from "../components/layout/GlobalSearch";
import { ThemeToggle } from "../components/layout/ThemeToggle";
import { MobileNav, MobileMenuButton } from "../components/layout/MobileNav";
import { RecentTickersStrip } from "../components/layout/RecentTickersStrip";
import { LeftWatchlistRail } from "../components/layout/LeftWatchlistRail";
import { MarketStatusPill } from "../components/layout/MarketStatusPill";
import { ShortcutsOverlay } from "../components/layout/ShortcutsOverlay";

/**
 * The single application shell (phase 1 task 1).
 *
 * Previously /chart/* rendered a terminal shell — nav, left rail, ticker tabs —
 * while every other route rendered a different site shell with a different nav
 * and no rail. Two apps under one domain. This is the one chrome; only the main
 * panel swaps between routes.
 */

const RAIL_COLLAPSED_KEY = "nse.rail_collapsed";

/** Phase 1 task 2 — every item resolves to a real route. */
const NAV = [
  { label: "Markets",    to: "/companies" },
  { label: "Screener",   to: "/screener" },
  { label: "Charts",     to: "/chart/EQTY" },
  { label: "Portfolios", to: "/portfolios" },
  { label: "Sectors",    to: "/sectors" },
  { label: "News",       to: "/news" },
  { label: "Calendar",   to: "/calendar" },
];

const navCls = ({ isActive }: { isActive: boolean }) =>
  `relative flex h-full items-center whitespace-nowrap px-3 text-sm font-medium transition-colors ${
    isActive
      ? "text-ink after:absolute after:inset-x-3 after:-bottom-px after:h-0.5 after:bg-accent"
      : "text-sub hover:text-ink"
  }`;

const ChevronIcon: FC<{ collapsed: boolean }> = ({ collapsed }) => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
       style={{ transform: collapsed ? "rotate(180deg)" : undefined }}>
    <polyline points="15 18 9 12 15 6" />
  </svg>
);

function readCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(RAIL_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

export const TerminalShell: FC<{ children: ReactNode }> = ({ children }) => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [railCollapsed, setRailCollapsed] = useState(readCollapsed);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const toggleRail = useCallback(() => {
    setRailCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(RAIL_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        // storage unavailable — the preference is best-effort
      }
      return next;
    });
  }, []);

  // "?" opens the shortcuts overlay. Ignored while typing so it cannot fire
  // from a search box. Cmd-K and "/" are owned by GlobalSearch itself.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (typing) return;
      if (e.key === "?") {
        e.preventDefault();
        setShortcutsOpen((v) => !v);
      }
      if (e.key === "Escape") setShortcutsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-50 h-12 border-b border-seam bg-canvas/95 backdrop-blur">
        <div className="mx-auto grid h-full max-w-[1600px] grid-cols-[auto_1fr_auto] items-center gap-2 px-3 sm:gap-4 sm:px-6 lg:px-8">
          <NseLogo />
          <div className="flex justify-center">
            <div className="w-full max-w-2xl">
              <GlobalSearch />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden md:block">
              <MarketStatusPill />
            </div>
            <div className="hidden sm:block">
              <ThemeToggle />
            </div>
            <button
              type="button"
              onClick={() => setShortcutsOpen(true)}
              className="hidden h-8 w-8 items-center justify-center rounded-full text-sub transition-colors hover:bg-raised hover:text-ink sm:flex"
              title="Keyboard shortcuts (?)"
              aria-label="Keyboard shortcuts"
            >
              <span className="text-sm font-semibold">?</span>
            </button>
            <MobileMenuButton onClick={() => setMobileOpen(true)} />
          </div>
        </div>
      </header>

      <nav
        className="sticky top-12 z-40 h-10 border-b border-seam bg-canvas/95 backdrop-blur"
        aria-label="Main navigation"
      >
        <div className="mx-auto flex h-full max-w-[1600px] items-center gap-1 overflow-x-auto px-4 scrollbar-none sm:px-6 lg:px-8">
          {NAV.map(({ label, to }) => (
            <NavLink key={label} to={to} className={navCls}>
              {label}
            </NavLink>
          ))}
        </div>
      </nav>

      <RecentTickersStrip />

      <div className="mx-auto flex max-w-[1600px] gap-4 px-3 py-4 sm:px-6 lg:px-8">
        <aside
          className={`hidden shrink-0 lg:block ${railCollapsed ? "w-10" : "w-60"}`}
          aria-label="Watchlist"
        >
          <button
            type="button"
            onClick={toggleRail}
            className="mb-2 flex h-7 w-full items-center justify-center rounded-md border border-seam text-sub transition-colors hover:bg-raised hover:text-ink"
            title={railCollapsed ? "Expand watchlist" : "Collapse watchlist"}
            aria-expanded={!railCollapsed}
          >
            <ChevronIcon collapsed={railCollapsed} />
          </button>
          {!railCollapsed && <LeftWatchlistRail />}
        </aside>

        <main className="min-w-0 flex-1">{children}</main>
      </div>

      <MobileNav isOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      <ShortcutsOverlay open={shortcutsOpen} onClose={() => setShortcutsOpen(false)} />
    </div>
  );
};
