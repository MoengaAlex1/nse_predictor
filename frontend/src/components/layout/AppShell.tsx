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

export type AppShellVariant = "default" | "investor";

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
