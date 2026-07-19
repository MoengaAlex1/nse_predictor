import type { FC } from "react";
import { Link } from "react-router-dom";

export const Navbar: FC = () => {
  return (
    <nav className="border-b border-slate-700 bg-slate-900">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/companies" className="text-lg font-bold text-sky-400">
              NSE Intelligence
            </Link>
            <Link
              to="/companies"
              className="text-sm text-slate-400 hover:text-slate-200 transition-colors"
            >
              Companies
            </Link>
          </div>
          {/* Auth buttons hidden — re-enable when auth is re-introduced */}
        </div>
      </div>
    </nav>
  );
};
