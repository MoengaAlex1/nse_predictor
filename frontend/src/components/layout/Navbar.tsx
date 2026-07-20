import type { FC } from "react";
import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext";

// ── Icons ─────────────────────────────────────────────────────────────────────
const SunIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="4" />
    <line x1="12" y1="2" x2="12" y2="4" />
    <line x1="12" y1="20" x2="12" y2="22" />
    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
    <line x1="2" y1="12" x2="4" y2="12" />
    <line x1="20" y1="12" x2="22" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
  </svg>
);

const MonitorIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2" />
    <line x1="8" y1="21" x2="16" y2="21" />
    <line x1="12" y1="17" x2="12" y2="21" />
  </svg>
);

const MoonIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
  </svg>
);

// ── Theme toggle pill ─────────────────────────────────────────────────────────
const THEME_OPTIONS = [
  { value: "light",  label: "Light mode",   icon: <SunIcon /> },
  { value: "system", label: "System theme",  icon: <MonitorIcon /> },
  { value: "dark",   label: "Dark mode",    icon: <MoonIcon /> },
] as const;

const ThemeToggle: FC = () => {
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

// ── Navbar ────────────────────────────────────────────────────────────────────
export const Navbar: FC = () => {
  return (
    <nav className="border-b border-rim bg-surface shadow-sm">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/companies" className="text-lg font-bold text-accent">
              NSE Intelligence
            </Link>
            <Link
              to="/companies"
              className="text-sm text-sub hover:text-ink transition-colors"
            >
              Companies
            </Link>
          </div>
          <ThemeToggle />
        </div>
      </div>
    </nav>
  );
};
