import { useMemo } from "react";
import type { FC } from "react";
import type { FinancialsDoc, FinancialResult, DividendEvent } from "../../types";
import { fmtCompact, EM_DASH } from "../../lib/format";

type Props = {
  financials: FinancialsDoc | null | undefined;
};

type Row = {
  fy: string;
  yearNum: number;
  revenue: number | null;
  netIncome: number | null;
  eps: number | null;
  bvps: number | null;
  dps: number | null;
  revYoY: number | null;
  niYoY: number | null;
  epsYoY: number | null;
};

// Extract "2024" from FY2024, FY 2024, 2024, 2024/25, etc.
function extractYear(period: string | null | undefined, periodEnd?: string | null): number | null {
  if (period) {
    const m = period.match(/(20\d{2}|19\d{2})/);
    if (m) return parseInt(m[1], 10);
  }
  if (periodEnd) {
    const y = periodEnd.slice(0, 4);
    if (/^\d{4}$/.test(y)) return parseInt(y, 10);
  }
  return null;
}

// Sum dividends[] by matching fiscal year. Falls back to announcement_date year
// when period/period_end are missing (older scraper output).
function dpsForYear(dividends: DividendEvent[], year: number): number | null {
  let total = 0;
  let found = false;
  for (const d of dividends) {
    if (d.amount_kes == null) continue;
    // Skip cash-less types
    if (d.type === "scrip" || d.type === "bonus" || d.type === "none") continue;
    const y = extractYear(d.period, d.period_end) ??
              (d.announcement_date ? parseInt(d.announcement_date.slice(0, 4), 10) : null);
    if (y === year) {
      total += d.amount_kes;
      found = true;
    }
  }
  return found ? total : null;
}

function pctChange(cur: number | null, prev: number | null): number | null {
  if (cur == null || prev == null || prev === 0) return null;
  return ((cur - prev) / Math.abs(prev)) * 100;
}

export const AnnualFinancialsTable: FC<Props> = ({ financials }) => {
  const rows = useMemo<Row[]>(() => {
    const annual = (financials?.annual ?? []).filter(
      (a: FinancialResult) => a.period_type === "annual" || !a.period_type,
    );
    const dividends = financials?.dividends ?? [];

    // Deduplicate by fiscal year — keep the entry with the most non-null values.
    const byYear = new Map<number, FinancialResult>();
    for (const a of annual) {
      const y = extractYear(a.period, a.period_end);
      if (y == null) continue;
      const existing = byYear.get(y);
      if (!existing) {
        byYear.set(y, a);
        continue;
      }
      const scoreA = [a.revenue_kes_mn, a.net_income_kes_mn, a.eps, a.bvps].filter((v) => v != null).length;
      const scoreE = [existing.revenue_kes_mn, existing.net_income_kes_mn, existing.eps, existing.bvps].filter(
        (v) => v != null,
      ).length;
      if (scoreA > scoreE) byYear.set(y, a);
    }

    const sortedYears = Array.from(byYear.keys()).sort((a, b) => b - a);
    const result: Row[] = [];
    for (let i = 0; i < sortedYears.length; i += 1) {
      const y = sortedYears[i];
      const a = byYear.get(y)!;
      const prev = sortedYears[i + 1] != null ? byYear.get(sortedYears[i + 1]!) : undefined;
      result.push({
        fy: `FY${y}`,
        yearNum: y,
        revenue: a.revenue_kes_mn ?? null,
        netIncome: a.net_income_kes_mn ?? null,
        eps: a.eps ?? null,
        bvps: a.bvps ?? null,
        dps: dpsForYear(dividends, y),
        revYoY: prev ? pctChange(a.revenue_kes_mn, prev.revenue_kes_mn) : null,
        niYoY:  prev ? pctChange(a.net_income_kes_mn, prev.net_income_kes_mn) : null,
        epsYoY: prev ? pctChange(a.eps, prev.eps) : null,
      });
    }
    return result;
  }, [financials]);

  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Annual Financials
        </p>
        <p className="mt-3 text-xs text-hint">
          No audited annual results extracted yet. The pipeline extracts EPS,
          revenue, and net income from company annual reports on file with the
          NSE — new PDFs are processed nightly.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Annual Financials
        </p>
        <span className="font-mono text-[10px] text-hint">
          {rows[rows.length - 1].fy} → {rows[0].fy} · {rows.length}{" "}
          {rows.length === 1 ? "year" : "years"}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead>
            <tr className="border-b border-seam text-[10px] uppercase tracking-wider text-hint">
              {/* Mobile shows Fiscal | Revenue | Net Income | EPS | DPS (5 cols).
                  Tablet (sm) adds YoY on Revenue + NI. Desktop (md) reveals
                  all YoY columns + BVPS. */}
              <th className="px-3 py-2 text-left font-semibold">Fiscal Year</th>
              <th className="px-3 py-2 text-right font-semibold">Revenue<span className="hidden sm:inline"> (KES mn)</span></th>
              <th className="hidden sm:table-cell px-3 py-2 text-right font-semibold">YoY</th>
              <th className="px-3 py-2 text-right font-semibold">Net Income</th>
              <th className="hidden sm:table-cell px-3 py-2 text-right font-semibold">YoY</th>
              <th className="px-3 py-2 text-right font-semibold">EPS<span className="hidden sm:inline"> (KES)</span></th>
              <th className="hidden md:table-cell px-3 py-2 text-right font-semibold">YoY</th>
              <th className="hidden md:table-cell px-3 py-2 text-right font-semibold">BVPS</th>
              <th className="px-3 py-2 text-right font-semibold">DPS</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={r.yearNum}
                className="border-b border-seam/50 last:border-0 hover:bg-raised/40"
              >
                <td className="px-3 py-2 font-mono font-semibold tabular-nums text-ink">{r.fy}</td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-ink">
                  {r.revenue != null ? fmtCompact(r.revenue) : EM_DASH}
                </td>
                <td className="hidden sm:table-cell px-3 py-2 text-right font-mono tabular-nums">
                  <YoyPill v={r.revYoY} />
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-ink">
                  {r.netIncome != null ? fmtCompact(r.netIncome) : EM_DASH}
                </td>
                <td className="hidden sm:table-cell px-3 py-2 text-right font-mono tabular-nums">
                  <YoyPill v={r.niYoY} />
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-ink">
                  {r.eps != null ? r.eps.toFixed(2) : EM_DASH}
                </td>
                <td className="hidden md:table-cell px-3 py-2 text-right font-mono tabular-nums">
                  <YoyPill v={r.epsYoY} />
                </td>
                <td className="hidden md:table-cell px-3 py-2 text-right font-mono tabular-nums text-sub">
                  {r.bvps != null ? r.bvps.toFixed(2) : EM_DASH}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-sub">
                  {r.dps != null ? r.dps.toFixed(2) : EM_DASH}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="border-t border-seam px-4 py-2 text-[10px] text-hint">
        Source: audited annual reports extracted via AI from company disclosures
        on the NSE. YoY = year-on-year change. DPS aggregates all cash dividends
        announced for the fiscal year.
      </p>
    </div>
  );
};

// Small coloured pill for a YoY % — green up, red down, muted otherwise.
const YoyPill: FC<{ v: number | null }> = ({ v }) => {
  if (v == null || !Number.isFinite(v)) {
    return <span className="text-hint">{EM_DASH}</span>;
  }
  const up = v >= 0;
  const cls = up
    ? "border-emerald-600/30 bg-emerald-500/10 text-emerald-500"
    : "border-red-600/30 bg-red-500/10 text-red-500";
  return (
    <span className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-semibold ${cls}`}>
      {up ? "+" : "−"}
      {Math.abs(v).toFixed(1)}%
    </span>
  );
};
