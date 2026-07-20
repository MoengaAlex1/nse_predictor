import type { FC } from "react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { CompanyLogo } from "../components/ui/CompanyLogo";
import { useCompanies } from "../hooks/useCompanies";
import type { CompanyDoc } from "../types";

const SECTORS = [
  "All",
  "Agricultural",
  "Automobiles and Accessories",
  "Banking",
  "Commercial and Services",
  "Construction and Allied",
  "Energy and Petroleum",
  "Exchange Traded Funds",
  "Insurance",
  "Investment",
  "Manufacturing and Allied",
  "Real Estate Investment Trust",
  "Telecommunication and Technology",
  "Transport and Storage",
];

const SIGNAL_STYLES: Record<string, { header: string; count: string; border: string }> = {
  BUY:  { header: "text-emerald-400", count: "bg-emerald-950/60 border-emerald-700", border: "border-emerald-900" },
  HOLD: { header: "text-amber-400",   count: "bg-amber-950/60  border-amber-700",   border: "border-amber-900"  },
  SELL: { header: "text-red-400",     count: "bg-red-950/60    border-red-700",     border: "border-red-900"    },
};

type ViewMode = "grid" | "board";

// ── Market summary strip ───────────────────────────────────────────────────────
type SummaryProps = {
  companies: CompanyDoc[];
};

const MarketSummary: FC<SummaryProps> = ({ companies }) => {
  const counts = useMemo(() => {
    const c = { BUY: 0, HOLD: 0, SELL: 0 };
    companies.forEach((co) => {
      if (co.signal === "BUY") c.BUY++;
      else if (co.signal === "HOLD") c.HOLD++;
      else if (co.signal === "SELL") c.SELL++;
    });
    return c;
  }, [companies]);

  const byChange = useMemo(
    () =>
      [...companies]
        .filter((c) => c.change_pct_today !== null)
        .sort((a, b) => (b.change_pct_today ?? 0) - (a.change_pct_today ?? 0)),
    [companies]
  );
  const gainers = byChange.slice(0, 3);
  const losers = [...byChange].reverse().slice(0, 3);

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {/* Signal counts */}
      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Signal Distribution
        </p>
        <div className="flex gap-2">
          {(["BUY", "HOLD", "SELL"] as const).map((s) => (
            <div
              key={s}
              className={`flex-1 rounded-md border px-2 py-2 text-center ${SIGNAL_STYLES[s].count}`}
            >
              <span className={`block text-2xl font-bold leading-none ${SIGNAL_STYLES[s].header}`}>
                {counts[s]}
              </span>
              <span className={`mt-0.5 block text-xs font-semibold ${SIGNAL_STYLES[s].header}`}>
                {s}
              </span>
            </div>
          ))}
        </div>
      </Card>

      {/* Top gainers */}
      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Top Gainers Today
        </p>
        {gainers.length === 0 ? (
          <p className="text-xs text-slate-500">No price data yet</p>
        ) : (
          <ul className="space-y-2">
            {gainers.map((c) => (
              <li key={c.id} className="flex items-center justify-between">
                <Link
                  to={`/company/${c.id}`}
                  className="text-sm font-medium text-slate-200 hover:text-sky-400"
                >
                  {c.short}
                  <span className="ml-1.5 text-xs text-slate-500">{c.name}</span>
                </Link>
                <span className="text-sm font-semibold text-emerald-400">
                  +{(c.change_pct_today ?? 0).toFixed(2)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Top losers */}
      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Top Losers Today
        </p>
        {losers.length === 0 ? (
          <p className="text-xs text-slate-500">No price data yet</p>
        ) : (
          <ul className="space-y-2">
            {losers.map((c) => (
              <li key={c.id} className="flex items-center justify-between">
                <Link
                  to={`/company/${c.id}`}
                  className="text-sm font-medium text-slate-200 hover:text-sky-400"
                >
                  {c.short}
                  <span className="ml-1.5 text-xs text-slate-500">{c.name}</span>
                </Link>
                <span className="text-sm font-semibold text-red-400">
                  {(c.change_pct_today ?? 0).toFixed(2)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
};

// ── Board view — three kanban columns ─────────────────────────────────────────
const BOARD_COLUMNS = [
  { signal: "BUY",  label: "Buy",  emoji: "↑" },
  { signal: "HOLD", label: "Hold", emoji: "→" },
  { signal: "SELL", label: "Sell", emoji: "↓" },
] as const;

const BoardView: FC<{ companies: CompanyDoc[] }> = ({ companies }) => {
  const bySignal = useMemo(() => {
    const map: Record<string, CompanyDoc[]> = { BUY: [], HOLD: [], SELL: [] };
    companies.forEach((c) => {
      if (c.signal === "BUY" || c.signal === "HOLD" || c.signal === "SELL") {
        map[c.signal].push(c);
      }
    });
    return map;
  }, [companies]);

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {BOARD_COLUMNS.map(({ signal, label, emoji }) => {
        const items = bySignal[signal];
        const styles = SIGNAL_STYLES[signal];
        return (
          <div key={signal} className={`rounded-xl border ${styles.border} bg-slate-900/50`}>
            <div className={`flex items-center justify-between rounded-t-xl border-b ${styles.border} px-4 py-3`}>
              <span className={`font-bold ${styles.header}`}>{emoji} {label}</span>
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${styles.count} ${styles.header}`}>
                {items.length}
              </span>
            </div>
            <div className="flex flex-col gap-2 p-3">
              {items.length === 0 && (
                <p className="py-6 text-center text-xs text-slate-600">No companies</p>
              )}
              {items.map((company) => (
                <CompanyCard key={company.id} company={company} showSignal={false} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ── Company card — shared by grid and board ────────────────────────────────────
const CompanyCard: FC<{ company: CompanyDoc; showSignal?: boolean }> = ({
  company,
  showSignal = true,
}) => {
  const change = company.change_pct_today;
  return (
    <Link to={`/company/${company.id}`}>
      <Card className="h-full cursor-pointer transition-colors hover:border-slate-500">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <CompanyLogo
                id={company.id}
                short={company.short}
                color={company.color}
                icon={company.icon}
                size="sm"
              />
              <span className="font-semibold text-slate-100">{company.short}</span>
            </div>
            <p className="mt-0.5 text-xs text-slate-500">{company.sector}</p>
          </div>
          {showSignal && company.signal && <SignalBadge signal={company.signal} />}
        </div>
        <div className="mt-3 flex items-end justify-between">
          <div>
            <p className="text-sm text-slate-400">{company.name}</p>
            {company.current_price !== null && (
              <p className="text-lg font-bold text-slate-100">
                KES {company.current_price.toFixed(2)}
              </p>
            )}
          </div>
          {change !== null && (
            <span
              className={`text-sm font-medium ${
                change >= 0 ? "text-emerald-400" : "text-red-400"
              }`}
            >
              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
            </span>
          )}
        </div>
      </Card>
    </Link>
  );
};

// ── View-toggle icon buttons ───────────────────────────────────────────────────
const GridIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="1" width="6" height="6" rx="1" />
    <rect x="9" y="1" width="6" height="6" rx="1" />
    <rect x="1" y="9" width="6" height="6" rx="1" />
    <rect x="9" y="9" width="6" height="6" rx="1" />
  </svg>
);

const BoardIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <rect x="1" y="1" width="4" height="14" rx="1" />
    <rect x="6" y="1" width="4" height="14" rx="1" />
    <rect x="11" y="1" width="4" height="14" rx="1" />
  </svg>
);

// ── Main page ─────────────────────────────────────────────────────────────────
export const Companies: FC = () => {
  const { data: companies, isLoading, isError } = useCompanies();
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("All");
  const [view, setView] = useState<ViewMode>("grid");

  const filtered = useMemo(() => {
    if (!companies) return [];
    return companies.filter((c) => {
      if (!c.name || !c.short || !c.ticker) return false;
      const q = search.toLowerCase();
      const matchSearch =
        c.name.toLowerCase().includes(q) ||
        c.short.toLowerCase().includes(q) ||
        c.ticker.toLowerCase().includes(q);
      const matchSector = sector === "All" || c.sector === sector;
      return matchSearch && matchSector;
    });
  }, [companies, search, sector]);

  return (
    <PageShell>
      <div className="space-y-6">
        {/* Page header */}
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-100">NSE Market</h1>
            <p className="mt-1 text-slate-400">
              {companies?.length ?? 0} companies tracked · Nairobi Securities Exchange
            </p>
          </div>

          {/* View toggle */}
          <div className="flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 p-1">
            <button
              type="button"
              title="Grid view"
              onClick={() => setView("grid")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                view === "grid"
                  ? "bg-slate-700 text-slate-100"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <GridIcon /> Grid
            </button>
            <button
              type="button"
              title="Board view"
              onClick={() => setView("board")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                view === "board"
                  ? "bg-slate-700 text-slate-100"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <BoardIcon /> Board
            </button>
          </div>
        </div>

        {isLoading && (
          <div className="flex justify-center py-16">
            <Spinner size="lg" />
          </div>
        )}

        {isError && (
          <Card className="border-red-800 bg-red-950/20">
            <p className="text-red-400">Failed to load companies.</p>
          </Card>
        )}

        {/* Market summary strip — always visible once data loads */}
        {companies && companies.length > 0 && (
          <MarketSummary companies={companies} />
        )}

        {/* Filters — search + sector (signal filter removed in board mode, columns are the signal) */}
        {!isLoading && companies && (
          <div className="flex flex-wrap gap-3">
            <input
              type="text"
              placeholder="Search companies..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-200 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
            />
            <select
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
            >
              {SECTORS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Grid view */}
        {!isLoading && view === "grid" && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((company) => (
              <CompanyCard key={company.id} company={company} />
            ))}
            {filtered.length === 0 && (
              <p className="col-span-3 py-8 text-center text-slate-500">
                No companies match your filters.
              </p>
            )}
          </div>
        )}

        {/* Board view */}
        {!isLoading && view === "board" && (
          <BoardView companies={filtered} />
        )}
      </div>
    </PageShell>
  );
};
