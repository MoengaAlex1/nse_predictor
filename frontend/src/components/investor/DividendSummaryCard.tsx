import { useMemo } from "react";
import type { FC } from "react";
import type { FinancialsDoc, DividendEvent } from "../../types";
import { fmtKes, fmtPct, EM_DASH } from "../../lib/format";

type Props = {
  financials: FinancialsDoc | null | undefined;
  currentPrice: number | null;   // for the current yield line
};

function extractYear(d: DividendEvent): number | null {
  if (d.period) {
    const m = d.period.match(/(20\d{2}|19\d{2})/);
    if (m) return parseInt(m[1], 10);
  }
  if (d.period_end) {
    const y = d.period_end.slice(0, 4);
    if (/^\d{4}$/.test(y)) return parseInt(y, 10);
  }
  if (d.announcement_date) return parseInt(d.announcement_date.slice(0, 4), 10);
  return null;
}

export const DividendSummaryCard: FC<Props> = ({ financials, currentPrice }) => {
  const stats = useMemo(() => {
    const divs = (financials?.dividends ?? []).filter(
      (d) => d.amount_kes != null && d.amount_kes > 0
             && d.type !== "scrip" && d.type !== "bonus" && d.type !== "none",
    );

    const nowYear = new Date().getFullYear();

    // 10-year total
    let total10y = 0;
    for (const d of divs) {
      const y = extractYear(d);
      if (y != null && y >= nowYear - 10 && d.amount_kes != null) total10y += d.amount_kes;
    }

    // TTM DPS: dividends announced in last 365 days
    let ttmDps = 0;
    const cutoffTtm = new Date();
    cutoffTtm.setDate(cutoffTtm.getDate() - 365);
    const cutoffIso = cutoffTtm.toISOString().slice(0, 10);
    for (const d of divs) {
      if (d.announcement_date >= cutoffIso && d.amount_kes != null) ttmDps += d.amount_kes;
    }
    const currentYield = currentPrice != null && currentPrice > 0 && ttmDps > 0
      ? (ttmDps / currentPrice) * 100 : null;

    // Consecutive years with at least one cash dividend
    const yearsSet = new Set<number>();
    for (const d of divs) {
      const y = extractYear(d);
      if (y != null) yearsSet.add(y);
    }
    let streak = 0;
    let checkYear = nowYear;
    // If no dividend yet this year, start from previous year
    if (!yearsSet.has(checkYear)) checkYear -= 1;
    while (yearsSet.has(checkYear)) {
      streak += 1;
      checkYear -= 1;
    }

    // Payout ratio: latest full FY where we have both eps and matched dividends
    let payoutRatio: number | null = null;
    const annuals = financials?.annual ?? [];
    for (const a of [...annuals].sort((x, y) => (y.period_end ?? "").localeCompare(x.period_end ?? ""))) {
      if (a.eps == null || a.eps <= 0) continue;
      const y = a.period_end ? parseInt(a.period_end.slice(0, 4), 10) : null;
      if (y == null) continue;
      let dpsForYear = 0;
      for (const d of divs) {
        if (extractYear(d) === y && d.amount_kes != null) dpsForYear += d.amount_kes;
      }
      if (dpsForYear > 0) {
        payoutRatio = (dpsForYear / a.eps) * 100;
        break;
      }
    }

    return {
      total10y: total10y > 0 ? total10y : null,
      ttmDps: ttmDps > 0 ? ttmDps : null,
      currentYield,
      streak,
      payoutRatio,
      hasData: divs.length > 0,
    };
  }, [financials, currentPrice]);

  if (!stats.hasData) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Dividend Summary
        </p>
        <p className="mt-2 text-[11px] text-hint">
          No cash dividend records yet.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
        Dividend Summary
      </p>

      <div className="mt-3 space-y-2.5">
        <StatRow label="Trailing yield" value={fmtPct(stats.currentYield)} highlight={stats.currentYield != null} />
        <StatRow label="TTM DPS" value={stats.ttmDps != null ? fmtKes(stats.ttmDps) : EM_DASH} />
        <StatRow label="10y total paid" value={stats.total10y != null ? fmtKes(stats.total10y) : EM_DASH} />
        <StatRow
          label="Consecutive years"
          value={
            stats.streak > 0 ? (
              <span className="inline-flex items-center gap-1">
                <span className="font-mono font-bold text-emerald-400">{stats.streak}y</span>
                {stats.streak >= 5 && (
                  <span className="rounded border border-emerald-600/40 bg-emerald-500/10 px-1 text-[9px] font-bold text-emerald-400">
                    ARISTOCRAT
                  </span>
                )}
              </span>
            ) : EM_DASH
          }
        />
        <StatRow
          label="Payout ratio"
          value={stats.payoutRatio != null ? fmtPct(stats.payoutRatio) : EM_DASH}
        />
      </div>
    </div>
  );
};

const StatRow: FC<{ label: string; value: React.ReactNode; highlight?: boolean }> = ({
  label, value, highlight,
}) => (
  <div className="flex items-baseline justify-between gap-2 border-b border-seam/60 pb-1.5 last:border-0 last:pb-0">
    <span className="text-[11px] text-hint">{label}</span>
    <span className={`font-mono text-xs tabular-nums ${highlight ? "font-bold text-ink" : "text-sub"}`}>
      {value}
    </span>
  </div>
);
