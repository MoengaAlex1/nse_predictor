import { useState, useRef, useEffect, useCallback } from "react";
import type { FC } from "react";
import { useNavigate } from "react-router-dom";
import { useCompanies } from "../../hooks/useCompanies";
import type { CompanyDoc } from "../../types";

const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

const XIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
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

type GlobalSearchProps = {
  // Which route to navigate to on selection. Default preserves the legacy
  // AppShell behaviour (/company/:ticker); the investor variant passes
  // "chart" so results open the focused chart view.
  targetRoute?: "company" | "dashboard" | "chart";
};

export const GlobalSearch: FC<GlobalSearchProps> = ({ targetRoute = "company" }) => {
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
      const path =
        targetRoute === "chart"
          ? `/chart/${ticker}`
          : targetRoute === "dashboard"
          ? `/dashboard/${ticker}`
          : `/company/${ticker}`;
      navigate(path);
      close();
    },
    [navigate, close, targetRoute],
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
          aria-label="Close search"
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
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-accent">{c.ticker}</span>
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
