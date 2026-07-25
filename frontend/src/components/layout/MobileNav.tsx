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
  { label: "Markets", to: "/companies" },
  { label: "Screener", to: "/companies" },
  { label: "News", to: "/companies" },
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
            aria-label="Close menu"
            onClick={onClose}
            className="text-muted transition-colors hover:text-ink"
          >
            <XIcon />
          </button>
        </div>
        <nav aria-label="Mobile navigation" className="flex-1 overflow-y-auto py-2">
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
