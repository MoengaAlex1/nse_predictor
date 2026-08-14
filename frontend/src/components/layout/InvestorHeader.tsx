import type { FC } from "react";
import { NseLogo } from "./NseLogo";
import { GlobalSearch } from "./GlobalSearch";
import { ThemeToggle } from "./ThemeToggle";
import { MobileMenuButton } from "./MobileNav";

const SettingsIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
  </svg>
);

const UserIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);

// Placeholder weather chip — real data source not wired yet.
// Keep the slot so the Phase D wiring drops in without relayout.
const WeatherPlaceholder: FC = () => (
  <div
    className="hidden items-center gap-1.5 rounded-full border border-seam bg-raised/60 px-2.5 py-1 text-xs text-muted sm:flex"
    title="Weather widget — coming soon"
  >
    <span aria-hidden="true">☁</span>
    <span className="font-medium">Nairobi</span>
    <span className="text-hint">—</span>
  </div>
);

// Placeholder user chip — auth wiring lands with watchlist in Phase C.
const UserChipPlaceholder: FC = () => (
  <button
    type="button"
    className="hidden items-center gap-1.5 rounded-full border border-seam bg-raised/60 px-2.5 py-1 text-xs font-medium text-sub transition-colors hover:text-ink sm:flex"
    title="Sign in — coming soon"
    disabled
  >
    <UserIcon />
    <span>Sign in</span>
  </button>
);

const SettingsButton: FC = () => (
  <button
    type="button"
    className="hidden h-8 w-8 items-center justify-center rounded-full text-sub transition-colors hover:bg-raised hover:text-ink sm:flex"
    title="Settings — coming soon"
    aria-label="Settings"
    disabled
  >
    <SettingsIcon />
  </button>
);

type InvestorHeaderProps = {
  onMobileMenuOpen: () => void;
};

export const InvestorHeader: FC<InvestorHeaderProps> = ({ onMobileMenuOpen }) => (
  <header className="sticky top-0 z-50 h-12 border-b border-seam bg-canvas/95 backdrop-blur">
    <div className="mx-auto grid h-full max-w-[1600px] grid-cols-[auto_1fr_auto] items-center gap-2 px-3 sm:gap-4 sm:px-6 lg:px-8">
      <NseLogo />

      <div className="flex justify-center">
        {/* Wider max on desktop, but never let it hog the whole mobile
            header — leaves room for the hamburger on 320px devices. */}
        <div className="w-full max-w-2xl">
          <GlobalSearch targetRoute="chart" />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <WeatherPlaceholder />
        <UserChipPlaceholder />
        <div className="hidden sm:block">
          <ThemeToggle />
        </div>
        <SettingsButton />
        <MobileMenuButton onClick={onMobileMenuOpen} />
      </div>
    </div>
  </header>
);
