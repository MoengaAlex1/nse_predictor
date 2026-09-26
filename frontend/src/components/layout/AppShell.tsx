import { useState } from "react";
import type { FC, ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { NseLogo } from "./NseLogo";
import { GlobalSearch } from "./GlobalSearch";
import { ThemeToggle } from "./ThemeToggle";
import { TickerTape } from "./TickerTape";
import { MobileNav, MobileMenuButton } from "./MobileNav";
import { InvestorHeader } from "./InvestorHeader";
import { SubNav } from "./SubNav";
import { RecentTickersStrip } from "./RecentTickersStrip";

const NAV_LINKS = [
  { label: "Markets",  to: "/companies", disabled: false },
  { label: "Screener", to: "/screener",  disabled: false },
  { label: "News",     to: "/companies", disabled: true  },
  { label: "Calendar", to: "/companies", disabled: true  },
];

const navLinkCls = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium transition-colors px-1 py-0.5 ${
    isActive ? "border-b-2 border-accent text-ink" : "text-sub hover:text-ink"
  }`;

export type AppShellVariant = "default" | "investor" | "workstation";

type AppShellProps = {
  children: ReactNode;
  variant?: AppShellVariant;
};

export const AppShell: FC<AppShellProps> = ({ children, variant = "default" }) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  if (variant === "investor") {
    return (
      <div className="min-h-screen bg-canvas text-ink">
        <InvestorHeader onMobileMenuOpen={() => setMobileOpen(true)} />
        <SubNav />
        <RecentTickersStrip />
        <main>{children}</main>
        <MobileNav isOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      </div>
    );
  }

  // Workstation variant: minimum chrome, maximum chart. Renders only a
  // compact 40px-tall top bar (logo + search + theme + sign-in) with no
  // SubNav / RecentTickersStrip / TickerTape / max-width padding. Used
  // for /chart/{ticker} where the TradingWorkstation component owns
  // everything below — its own symbol search, timeframe controls, and
  // right sidebar make the extra AppShell chrome redundant.
  if (variant === "workstation") {
    return (
      <div className="flex min-h-screen flex-col bg-canvas text-ink">
        <header className="sticky top-0 z-50 h-10 shrink-0 border-b border-seam bg-canvas/95 backdrop-blur">
          <div className="mx-auto flex h-full max-w-none items-center justify-between px-3 sm:px-4">
            <div className="flex items-center gap-3">
              <NseLogo />
              {/* Compact primary nav — three shortcut links so users can
                  get back to Home / Screener / Markets without extra
                  vertical rows. Hidden on narrow widths. */}
              <nav className="hidden items-center gap-4 md:flex" aria-label="Main navigation">
                {NAV_LINKS.filter(l => !l.disabled).map(({ label, to }) => (
                  <NavLink key={label} to={to} className={navLinkCls}>
                    {label}
                  </NavLink>
                ))}
              </nav>
            </div>
            <div className="flex items-center gap-2">
              {/* Visible build tag so cache issues can be diagnosed at a
                  glance. Injected at build time via Vite's define hook. */}
              <span
                className="hidden font-mono text-[10px] text-hint sm:inline"
                title="Deployed build tag — if this looks old, hard-refresh (Ctrl+Shift+R)"
              >
                {typeof __BUILD_TAG__ !== "undefined" ? __BUILD_TAG__ : "dev"}
              </span>
              <GlobalSearch />
              <div className="hidden sm:block">
                <ThemeToggle />
              </div>
              <MobileMenuButton onClick={() => setMobileOpen(true)} />
            </div>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <MobileNav isOpen={mobileOpen} onClose={() => setMobileOpen(false)} />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <header className="sticky top-0 z-50 h-14 border-b border-seam bg-canvas/95 backdrop-blur">
        <div className="mx-auto flex h-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <NseLogo />

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
