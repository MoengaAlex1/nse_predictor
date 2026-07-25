import type { FC } from "react";
import { Link } from "react-router-dom";
import { ThemeToggle } from "./ThemeToggle";

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
