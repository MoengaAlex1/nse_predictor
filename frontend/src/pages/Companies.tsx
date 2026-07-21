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

const SECTOR_ORDER = [
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
  BUY:  { header: "text-emerald-500", count: "bg-emerald-500/10 border-emerald-500/30", border: "border-emerald-900/60" },
  HOLD: { header: "text-amber-500",   count: "bg-amber-500/10  border-amber-500/30",   border: "border-amber-900/60"   },
  SELL: { header: "text-red-500",     count: "bg-red-500/10    border-red-500/30",     border: "border-red-900/60"     },
};

type ViewMode = "grid" | "board";

// ── Market summary strip ───────────────────────────────────────────────────────
type SummaryProps = { companies: CompanyDoc[] };

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
      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">
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

      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">
          Top Gainers Today
        </p>
        {gainers.length === 0 ? (
          <p className="text-xs text-muted">No price data yet</p>
        ) : (
          <ul className="space-y-2">
            {gainers.map((c) => (
              <li key={c.id} className="flex items-center justify-between">
                <Link to={`/company/${c.id}`} className="text-sm font-medium text-sub hover:text-accent">
                  {c.short}
                  <span className="ml-1.5 text-xs text-muted">{c.name}</span>
                </Link>
                <span className="text-sm font-semibold text-emerald-500">
                  +{(c.change_pct_today ?? 0).toFixed(2)}%
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted">
          Top Losers Today
        </p>
        {losers.length === 0 ? (
          <p className="text-xs text-muted">No price data yet</p>
        ) : (
          <ul className="space-y-2">
            {losers.map((c) => (
              <li key={c.id} className="flex items-center justify-between">
                <Link to={`/company/${c.id}`} className="text-sm font-medium text-sub hover:text-accent">
                  {c.short}
                  <span className="ml-1.5 text-xs text-muted">{c.name}</span>
                </Link>
                <span className="text-sm font-semibold text-red-500">
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

// ── Board view ─────────────────────────────────────────────────────────────────
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
          <div key={signal} className={`rounded-xl border ${styles.border} bg-surface`}>
            <div className={`flex items-center justify-between rounded-t-xl border-b ${styles.border} px-4 py-3`}>
              <span className={`font-bold ${styles.header}`}>{emoji} {label}</span>
              <span className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${styles.count} ${styles.header}`}>
                {items.length}
              </span>
            </div>
            <div className="flex flex-col gap-2 p-3">
              {items.length === 0 && (
                <p className="py-6 text-center text-xs text-hint">No companies</p>
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

// ── Company card ───────────────────────────────────────────────────────────────
const CompanyCard: FC<{ company: CompanyDoc; showSignal?: boolean }> = ({
  company,
  showSignal = true,
}) => {
  const change = company.change_pct_today;
  return (
    <Link to={`/company/${company.id}`}>
      <Card className="h-full cursor-pointer transition-colors hover:border-sub/40">
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
              <span className="font-semibold text-ink">{company.short}</span>
            </div>
            <p className="mt-0.5 text-xs text-muted">{company.sector}</p>
          </div>
          {showSignal && company.signal && <SignalBadge signal={company.signal} />}
        </div>
        <div className="mt-3 flex items-end justify-between">
          <div>
            <p className="text-sm text-sub">{company.name}</p>
            {company.current_price !== null && (
              <p className="text-lg font-bold text-ink">
                KES {company.current_price.toFixed(2)}
              </p>
            )}
          </div>
          {change !== null && (
            <span className={`text-sm font-medium ${change >= 0 ? "text-emerald-500" : "text-red-500"}`}>
              {change >= 0 ? "+" : ""}{change.toFixed(2)}%
            </span>
          )}
        </div>
      </Card>
    </Link>
  );
};

// ── View-toggle icons ──────────────────────────────────────────────────────────
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

// ── Sector pill ────────────────────────────────────────────────────────────────
const SectorPill: FC<{ label: string; count: number; active: boolean; onClick: () => void }> = ({
  label,
  count,
  active,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
      active
        ? "border-accent bg-accent/10 text-accent"
        : "border-rim bg-raised text-sub hover:border-sub/40 hover:text-ink"
    }`}
  >
    {label}
    <span
      className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none ${
        active ? "bg-accent/20 text-accent" : "bg-surface text-muted"
      }`}
    >
      {count}
    </span>
  </button>
);

// ── Grouped grid (All sectors) ─────────────────────────────────────────────────
const GroupedGrid: FC<{ companies: CompanyDoc[] }> = ({ companies }) => {
  const groups = useMemo(() => {
    const map = new Map<string, CompanyDoc[]>();
    companies.forEach((c) => {
      const s = c.sector || "Other";
      if (!map.has(s)) map.set(s, []);
      map.get(s)!.push(c);
    });
    return SECTOR_ORDER
      .filter((s) => map.has(s))
      .map((s) => ({ sector: s, items: map.get(s)! }))
      .concat(
        map.has("Other") ? [{ sector: "Other", items: map.get("Other")! }] : []
      );
  }, [companies]);

  if (groups.length === 0) {
    return <p className="py-8 text-center text-muted">No companies match your filters.</p>;
  }

  return (
    <div className="space-y-8">
      {groups.map(({ sector, items }) => (
        <div key={sector}>
          <div className="mb-3 flex items-center gap-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">{sector}</h2>
            <span className="text-xs text-hint">{items.length}</span>
            <div className="h-px flex-1 bg-rim" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((company) => (
              <CompanyCard key={company.id} company={company} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────
export const Companies: FC = () => {
  const { data: companies, isLoading, isError } = useCompanies();
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("All");
  const [view, setView] = useState<ViewMode>("grid");

  // Build sector pill list with counts from actual data
  const sectorPills = useMemo(() => {
    if (!companies) return [{ label: "All", count: 0 }];
    const counts = new Map<string, number>();
    companies.forEach((c) => {
      if (c.sector) counts.set(c.sector, (counts.get(c.sector) ?? 0) + 1);
    });
    const pills = [{ label: "All", count: companies.length }];
    SECTOR_ORDER.forEach((s) => {
      if (counts.has(s)) pills.push({ label: s, count: counts.get(s)! });
    });
    return pills;
  }, [companies]);

  const filtered = useMemo(() => {
    if (!companies) return [];
    return companies.filter((c) => {
      if (!c.name || !c.short || !c.ticker) return false;
      const q = search.toLowerCase();
      const matchSearch =
        !q ||
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
            <h1 className="text-3xl font-bold text-ink">NSE Market</h1>
            <p className="mt-1 text-sub">
              {companies?.length ?? 0} companies tracked · Nairobi Securities Exchange
            </p>
          </div>

          {/* View toggle */}
          <div className="flex items-center gap-1 rounded-lg border border-rim bg-raised p-1">
            <button
              type="button"
              title="Grid view"
              onClick={() => setView("grid")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                view === "grid" ? "bg-surface text-ink shadow-sm" : "text-sub hover:text-ink"
              }`}
            >
              <GridIcon /> Grid
            </button>
            <button
              type="button"
              title="Board view"
              onClick={() => setView("board")}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                view === "board" ? "bg-surface text-ink shadow-sm" : "text-sub hover:text-ink"
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

        {companies && companies.length > 0 && (
          <MarketSummary companies={companies} />
        )}

        {!isLoading && companies && (
          <div className="space-y-3">
            {/* Search */}
            <input
              type="text"
              placeholder="Search companies..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-rim bg-raised px-4 py-2 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none sm:w-72"
            />

            {/* Sector pills */}
            <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
              {sectorPills.map(({ label, count }) => (
                <SectorPill
                  key={label}
                  label={label}
                  count={count}
                  active={sector === label}
                  onClick={() => setSector(label)}
                />
              ))}
            </div>
          </div>
        )}

        {!isLoading && view === "grid" && (
          sector === "All" && !search
            ? <GroupedGrid companies={filtered} />
            : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {filtered.map((company) => (
                  <CompanyCard key={company.id} company={company} />
                ))}
                {filtered.length === 0 && (
                  <p className="col-span-3 py-8 text-center text-muted">
                    No companies match your filters.
                  </p>
                )}
              </div>
            )
        )}

        {!isLoading && view === "board" && (
          <BoardView companies={filtered} />
        )}
      </div>
    </PageShell>
  );
};
