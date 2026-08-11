import type { FC } from "react";
import { NavLink } from "react-router-dom";

type SubNavLink = {
  label: string;
  to: string;
  disabled?: boolean;
};

const LINKS: SubNavLink[] = [
  { label: "Discover", to: "/" },
  { label: "Markets", to: "/companies" },
  { label: "Screener", to: "/screener" },
  { label: "Portfolios", to: "/portfolios", disabled: true },
  { label: "Sectors", to: "/sectors", disabled: true },
];

const linkCls = ({ isActive }: { isActive: boolean }) =>
  `relative flex h-full items-center px-3 text-sm font-medium transition-colors ${
    isActive
      ? "text-ink after:absolute after:inset-x-3 after:-bottom-px after:h-0.5 after:bg-accent"
      : "text-sub hover:text-ink"
  }`;

export const SubNav: FC = () => (
  <div className="sticky top-12 z-40 h-10 border-b border-seam bg-canvas/95 backdrop-blur">
    <div className="mx-auto flex h-full max-w-[1600px] items-center gap-1 px-4 sm:px-6 lg:px-8">
      {LINKS.map(({ label, to, disabled }) =>
        disabled ? (
          <span
            key={label}
            className="flex h-full cursor-not-allowed items-center px-3 text-sm font-medium text-hint"
            title="Coming soon"
          >
            {label}
          </span>
        ) : (
          <NavLink key={label} to={to} end={to === "/"} className={linkCls}>
            {label}
          </NavLink>
        ),
      )}
    </div>
  </div>
);
