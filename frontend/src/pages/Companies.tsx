import type { FC } from "react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { useCompanies } from "../hooks/useCompanies";
import type { CompanyDoc } from "../types";

const SECTORS = [
  "All", "Banking", "Insurance", "Manufacturing", "Energy", "Telecom",
  "Agricultural", "Construction", "Commercial", "Investment", "REIT",
  "Beverages", "Automobiles", "Tourism", "Transport",
];
const SIGNALS = ["All", "BUY", "HOLD", "SELL"] as const;
type SignalFilter = (typeof SIGNALS)[number];

export const Companies: FC = () => {
  const { data: companies, isLoading, isError } = useCompanies();
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("All");
  const [signal, setSignal] = useState<SignalFilter>("All");

  const filtered = useMemo(() => {
    if (!companies) return [];
    return companies.filter((c) => {
      const q = search.toLowerCase();
      const matchSearch =
        c.name.toLowerCase().includes(q) ||
        c.short.toLowerCase().includes(q) ||
        c.ticker.toLowerCase().includes(q);
      const matchSector = sector === "All" || c.sector === sector;
      const matchSignal = signal === "All" || c.signal === signal;
      return matchSearch && matchSector && matchSignal;
    });
  }, [companies, search, sector, signal]);

  return (
    <PageShell>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-100">NSE Companies</h1>
          <p className="mt-1 text-slate-400">
            {companies?.length ?? 0} companies tracked
          </p>
        </div>

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
          <select
            value={signal}
            onChange={(e) => setSignal(e.target.value as SignalFilter)}
            className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            {SIGNALS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
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

        {!isLoading && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((company) => (
              <CompanyCard key={company.id} company={company} />
            ))}
            {filtered.length === 0 && !isLoading && (
              <p className="col-span-3 py-8 text-center text-slate-500">
                No companies match your filters.
              </p>
            )}
          </div>
        )}
      </div>
    </PageShell>
  );
};

const CompanyCard: FC<{ company: CompanyDoc }> = ({ company }) => {
  const change = company.change_pct_today;
  return (
    <Link to={`/company/${company.id}`}>
      <Card className="h-full cursor-pointer transition-colors hover:border-slate-500">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xl">{company.icon}</span>
              <span className="font-semibold text-slate-100">{company.short}</span>
            </div>
            <p className="mt-0.5 text-xs text-slate-500">{company.sector}</p>
          </div>
          {company.signal && <SignalBadge signal={company.signal} />}
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
              {change >= 0 ? "+" : ""}
              {change.toFixed(2)}%
            </span>
          )}
        </div>
      </Card>
    </Link>
  );
};
