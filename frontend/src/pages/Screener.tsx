import { useMemo, useState } from "react";
import type { FC } from "react";
import { Link } from "react-router-dom";
import { useCompanies } from "../hooks/useCompanies";
import { useAllFinancials, useAllFundamentals } from "../hooks/useScreener";
import { CompanyLogo } from "../components/ui/CompanyLogo";
import { Spinner } from "../components/ui/Spinner";
import { fmtCompact, fmtCompactKes, fmtPrice, fmtPct, arrow, trendClass, EM_DASH } from "../lib/format";
import type { CompanyDoc, FinancialsDoc, FundamentalsDoc } from "../types";

// ── Row shape and computation ─────────────────────────────────────────────

type ScreenerRow = {
  id: string;
  ticker: string;
  short: string;
  name: string;
  sector: string;
  color: string;
  icon: string;
  price: number | null;
  priceIsFallback: boolean;
  priceAsOf: string | null;
  changePct: number | null;
  signal: "BUY" | "HOLD" | "SELL" | null;
  eps: number | null;
  epsPeriod: string | null;
  pe: number | null;
  sharesMn: number | null;
  marketCapKes: number | null;
  divYieldPct: number | null;
  latestDivDate: string | null;
};

function buildRow(
  c: CompanyDoc,
  fin: FinancialsDoc | undefined,
  fund: FundamentalsDoc | undefined,
): ScreenerRow {
  // Live price wins; otherwise fall back to the last known VWAP so Market
  // Cap still computes for tickers with a thin intraday feed. Flagged as
  // stale in the UI via a chip so users know the source.
  const livePrice = c.current_price ?? null;
  const fallbackPrice = c.last_known_price ?? null;
  const price = livePrice ?? fallbackPrice;
  const priceIsFallback = livePrice == null && fallbackPrice != null;
  const changePct = c.change_pct_today ?? null;
  const sharesMn = fund?.shares_outstanding_mn ?? null;
  const marketCap = price != null && sharesMn != null ? price * sharesMn * 1_000_000 : null;

  // Latest annual with positive EPS (audited > interim)
  const annuals = fin?.annual ? [...fin.annual] : [];
  annuals.sort((a, b) => (b.period_end ?? "").localeCompare(a.period_end ?? ""));
  const latestAnnual = annuals.find((r) => r.eps != null && r.eps > 0);
  const eps = latestAnnual?.eps ?? null;
  const epsPeriod = latestAnnual?.period ?? null;
  const pe = price != null && eps != null && eps > 0 ? price / eps : null;

  // TTM dividend yield = sum of last-365-days amount_kes ÷ price
  let divYieldPct: number | null = null;
  let latestDivDate: string | null = null;
  if (fin?.dividends && price != null && price > 0) {
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - 1);
    const cutIso = cutoff.toISOString().slice(0, 10);
    let total = 0;
    fin.dividends.forEach((d) => {
      if (d.announcement_date >= cutIso && d.type !== "none" && d.amount_kes != null) {
        total += d.amount_kes;
      }
    });
    if (total > 0) divYieldPct = (total / price) * 100;

    const dated = fin.dividends
      .filter((d) => d.type !== "none" && (d.ex_date || d.period_end || d.announcement_date))
      .sort((a, b) => {
        const av = a.ex_date ?? a.period_end ?? a.announcement_date ?? "";
        const bv = b.ex_date ?? b.period_end ?? b.announcement_date ?? "";
        return bv.localeCompare(av);
      });
    latestDivDate = dated[0]?.ex_date ?? dated[0]?.period_end ?? dated[0]?.announcement_date ?? null;
  }

  return {
    id: c.id,
    ticker: c.ticker,
    short: c.short,
    name: c.name,
    sector: c.sector,
    color: c.color,
    icon: c.icon,
    price,
    priceIsFallback,
    priceAsOf: priceIsFallback ? c.last_known_price_as_of ?? null : c.price_date ?? null,
    changePct,
    signal: c.signal,
    eps,
    epsPeriod,
    pe,
    sharesMn,
    marketCapKes: marketCap,
    divYieldPct,
    latestDivDate,
  };
}

// ── Sortable header cell ──────────────────────────────────────────────────

type SortKey =
  | "ticker" | "sector" | "price" | "changePct"
  | "marketCapKes" | "sharesMn" | "eps" | "pe" | "divYieldPct" | "signal";

const SortIcon: FC<{ dir: "asc" | "desc" | null }> = ({ dir }) => (
  <span className="ml-1 inline-block w-2 text-hint">
    {dir === "asc" ? "▲" : dir === "desc" ? "▼" : ""}
  </span>
);

const HeaderCell: FC<{
  label: string;
  sortKey: SortKey;
  activeKey: SortKey;
  dir: "asc" | "desc";
  onSort: (k: SortKey) => void;
  numeric?: boolean;
}> = ({ label, sortKey, activeKey, dir, onSort, numeric }) => {
  const active = activeKey === sortKey;
  return (
    <th
      onClick={() => onSort(sortKey)}
      className={`cursor-pointer whitespace-nowrap px-3 py-2 text-[10px] font-semibold uppercase tracking-wider transition-colors hover:text-ink ${
        active ? "text-ink" : "text-muted"
      } ${numeric ? "text-right" : "text-left"}`}
    >
      {label}
      <SortIcon dir={active ? dir : null} />
    </th>
  );
};

// ── Sector pill ───────────────────────────────────────────────────────────

const SECTOR_ORDER = [
  "Agricultural", "Automobiles and Accessories", "Banking",
  "Commercial and Services", "Construction and Allied",
  "Energy and Petroleum", "Exchange Traded Funds", "Insurance",
  "Investment", "Investment Services", "Manufacturing and Allied",
  "Real Estate Investment Trust", "Telecommunication and Technology",
];

const SectorPill: FC<{ label: string; count: number; active: boolean; onClick: () => void }> = ({
  label, count, active, onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium transition-colors ${
      active
        ? "border-accent bg-accent/10 text-accent"
        : "border-rim bg-raised text-sub hover:border-sub/40 hover:text-ink"
    }`}
  >
    {label}
    <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none ${
      active ? "bg-accent/20 text-accent" : "bg-surface text-muted"
    }`}>
      {count}
    </span>
  </button>
);

// ── Main page ────────────────────────────────────────────────────────────

export const Screener: FC = () => {
  const { data: companies = [], isLoading: coLoading } = useCompanies();
  const { data: financialsMap } = useAllFinancials();
  const { data: fundamentalsMap } = useAllFundamentals();

  const [search, setSearch] = useState("");
  const [sector, setSector] = useState<string>("All");
  const [signalFilter, setSignalFilter] = useState<string>("All");
  const [sortKey, setSortKey] = useState<SortKey>("marketCapKes");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const rows = useMemo<ScreenerRow[]>(() => {
    return companies.map((c) => buildRow(c, financialsMap?.get(c.id), fundamentalsMap?.get(c.id)));
  }, [companies, financialsMap, fundamentalsMap]);

  const sectorCounts = useMemo(() => {
    const map = new Map<string, number>();
    rows.forEach((r) => { if (r.sector) map.set(r.sector, (map.get(r.sector) ?? 0) + 1); });
    return map;
  }, [rows]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => {
      if (sector !== "All" && r.sector !== sector) return false;
      if (signalFilter !== "All" && r.signal !== signalFilter) return false;
      if (!q) return true;
      return (
        r.ticker.toLowerCase().includes(q) ||
        r.short.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q)
      );
    });
  }, [rows, search, sector, signalFilter]);

  const sorted = useMemo(() => {
    const dir = sortDir === "asc" ? 1 : -1;
    return [...filtered].sort((a, b) => {
      let av: string | number | null = null;
      let bv: string | number | null = null;
      switch (sortKey) {
        case "ticker":       av = a.ticker; bv = b.ticker; break;
        case "sector":       av = a.sector; bv = b.sector; break;
        case "signal":       av = a.signal ?? ""; bv = b.signal ?? ""; break;
        case "price":        av = a.price;         bv = b.price;         break;
        case "changePct":    av = a.changePct;     bv = b.changePct;     break;
        case "marketCapKes": av = a.marketCapKes;  bv = b.marketCapKes;  break;
        case "sharesMn":     av = a.sharesMn;      bv = b.sharesMn;      break;
        case "eps":          av = a.eps;           bv = b.eps;           break;
        case "pe":           av = a.pe;            bv = b.pe;            break;
        case "divYieldPct":  av = a.divYieldPct;   bv = b.divYieldPct;   break;
      }
      // Nulls always at the bottom regardless of sort direction
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "string" && typeof bv === "string") return av.localeCompare(bv) * dir;
      return ((av as number) - (bv as number)) * dir;
    });
  }, [filtered, sortKey, sortDir]);

  const handleSort = (k: SortKey) => {
    if (k === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setSortDir(k === "ticker" || k === "sector" ? "asc" : "desc");
    }
  };

  const sectorPills = [
    { label: "All", count: rows.length, sector: "All" },
    ...SECTOR_ORDER.filter((s) => sectorCounts.has(s)).map((s) => ({
      label: s, count: sectorCounts.get(s) ?? 0, sector: s,
    })),
  ];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-ink">Market Screener</h1>
        <p className="mt-1 text-xs text-sub">
          {sorted.length} of {rows.length} companies · sort by any column · click a row for full detail
          <span className="ml-2 text-hint">
            (prices marked <span className="text-hint">*</span> are last-known VWAP for thinly-traded tickers)
          </span>
        </p>
      </div>

      {/* Filters */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            placeholder="Search ticker, short name, or company…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full max-w-sm rounded-lg border border-rim bg-raised px-3 py-1.5 text-sm text-ink placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <div className="flex items-center gap-1 rounded-lg border border-rim bg-raised p-0.5">
            {(["All", "BUY", "HOLD", "SELL"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSignalFilter(s)}
                className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                  signalFilter === s
                    ? s === "BUY" ? "bg-emerald-500/20 text-emerald-500"
                    : s === "SELL" ? "bg-red-500/20 text-red-500"
                    : s === "HOLD" ? "bg-amber-500/20 text-amber-500"
                    : "bg-accent/20 text-accent"
                    : "text-muted hover:text-ink"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
          {sectorPills.map((p) => (
            <SectorPill
              key={p.sector}
              label={p.label}
              count={p.count}
              active={sector === p.sector}
              onClick={() => setSector(p.sector)}
            />
          ))}
        </div>
      </div>

      {coLoading ? (
        <div className="flex justify-center py-16"><Spinner size="lg" /></div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-rim bg-surface">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-seam bg-raised/40">
                <tr>
                  <HeaderCell label="Ticker" sortKey="ticker" activeKey={sortKey} dir={sortDir} onSort={handleSort} />
                  <HeaderCell label="Sector" sortKey="sector" activeKey={sortKey} dir={sortDir} onSort={handleSort} />
                  <HeaderCell label="Price" sortKey="price" activeKey={sortKey} dir={sortDir} onSort={handleSort} numeric />
                  <HeaderCell label="Δ Today" sortKey="changePct" activeKey={sortKey} dir={sortDir} onSort={handleSort} numeric />
                  <HeaderCell label="Market Cap" sortKey="marketCapKes" activeKey={sortKey} dir={sortDir} onSort={handleSort} numeric />
                  <HeaderCell label="Shares (Mn)" sortKey="sharesMn" activeKey={sortKey} dir={sortDir} onSort={handleSort} numeric />
                  <HeaderCell label="EPS (TTM)" sortKey="eps" activeKey={sortKey} dir={sortDir} onSort={handleSort} numeric />
                  <HeaderCell label="P/E" sortKey="pe" activeKey={sortKey} dir={sortDir} onSort={handleSort} numeric />
                  <HeaderCell label="Div Yield" sortKey="divYieldPct" activeKey={sortKey} dir={sortDir} onSort={handleSort} numeric />
                  <HeaderCell label="Signal" sortKey="signal" activeKey={sortKey} dir={sortDir} onSort={handleSort} />
                </tr>
              </thead>
              <tbody className="divide-y divide-seam/50">
                {sorted.map((r) => (
                  <tr key={r.id} className="transition-colors hover:bg-raised/40">
                    <td className="px-3 py-2">
                      <Link to={`/chart/${r.id}`} className="flex items-center gap-2">
                        <CompanyLogo id={r.id} short={r.short} color={r.color} icon={r.icon} size="sm" />
                        <div className="min-w-0">
                          <div className="flex items-baseline gap-2">
                            <span className="font-semibold text-ink">{r.short}</span>
                            <span className="font-mono text-[10px] text-hint">{r.ticker}</span>
                          </div>
                          <p className="truncate text-[11px] text-muted">{r.name}</p>
                        </div>
                      </Link>
                    </td>
                    <td className="px-3 py-2 text-xs text-sub">
                      <span className="truncate">{r.sector || EM_DASH}</span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-ink">
                      {r.price != null ? (
                        <span
                          className={r.priceIsFallback ? "text-hint" : ""}
                          title={r.priceIsFallback && r.priceAsOf ? `Last known price as of ${r.priceAsOf}` : undefined}
                        >
                          {fmtPrice(r.price)}
                          {r.priceIsFallback && <span className="ml-1 text-[9px] text-hint">*</span>}
                        </span>
                      ) : EM_DASH}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono tabular-nums font-semibold ${trendClass(r.changePct)}`}>
                      {r.changePct != null ? `${arrow(r.changePct >= 0)} ${fmtPct(r.changePct)}` : EM_DASH}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-ink">
                      {r.marketCapKes != null ? fmtCompactKes(r.marketCapKes) : EM_DASH}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-sub">
                      {r.sharesMn != null ? fmtCompact(r.sharesMn) : EM_DASH}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-ink" title={r.epsPeriod ?? undefined}>
                      {r.eps != null ? r.eps.toFixed(2) : EM_DASH}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-ink">
                      {r.pe != null ? `${r.pe.toFixed(1)}×` : EM_DASH}
                    </td>
                    <td className="px-3 py-2 text-right font-mono tabular-nums text-emerald-500">
                      {r.divYieldPct != null ? `${r.divYieldPct.toFixed(2)}%` : EM_DASH}
                    </td>
                    <td className="px-3 py-2">
                      {r.signal ? (
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                          r.signal === "BUY" ? "bg-emerald-500/10 text-emerald-500"
                          : r.signal === "SELL" ? "bg-red-500/10 text-red-500"
                          : "bg-amber-500/10 text-amber-500"
                        }`}>
                          {r.signal}
                        </span>
                      ) : (
                        <span className="text-hint">{EM_DASH}</span>
                      )}
                    </td>
                  </tr>
                ))}
                {sorted.length === 0 && (
                  <tr>
                    <td colSpan={10} className="px-4 py-8 text-center text-sm text-muted">
                      No companies match your filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
