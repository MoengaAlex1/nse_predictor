import type { FC } from "react";
import type { RtdbPricePoint } from "../hooks/useHistoricalPrices";

interface Props {
  latest: RtdbPricePoint | null;
  currentPrice?: number | null;
  /**
   * When true, the panel renders as a vertical label→value list instead of a
   * grid of chip tiles. Use this inside the CompanyDeepDive sidebar (360px)
   * where the 4- and 8-column grid variants collapse into unreadable narrow
   * cells with the "KES 35.40" values wrapping under their labels.
   */
  compact?: boolean;
}

const fmtVol = (v: number | null): string => {
  if (v == null) return "—";
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toLocaleString();
};

const fmtKES = (v: number | null): string =>
  v != null ? `KES ${v.toFixed(2)}` : "—";

/** Tile used in the full-width grid variant. Padded, self-contained. */
const Metric: FC<{ label: string; value: string; accent?: string }> = ({ label, value, accent }) => (
  <div className="rounded-lg border border-seam bg-raised/50 p-3">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</p>
    <p className={`mt-0.5 font-mono text-sm font-semibold ${accent ?? "text-ink"}`}>{value}</p>
  </div>
);

/**
 * Row used in the compact / sidebar variant. Label on the left, value on the
 * right, hairline divider between rows. No chip borders — the panel's own
 * container is the visual boundary, and duplicating it per row wastes width.
 */
const MetricRow: FC<{ label: string; value: string; accent?: string }> = ({ label, value, accent }) => (
  <div className="flex items-center justify-between border-b border-seam/50 py-1.5 last:border-b-0">
    <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</span>
    <span className={`font-mono text-xs font-semibold ${accent ?? "text-ink"}`}>{value}</span>
  </div>
);

export const MarketQuotePanel: FC<Props> = ({ latest, currentPrice, compact = false }) => {
  if (!latest) return null;

  const close = latest.c ?? currentPrice ?? null;
  const chg = latest.ch ?? (close != null && latest.pc != null ? close - latest.pc : null);
  const chgPct = latest.pch ?? (chg != null && latest.pc && latest.pc > 0 ? (chg / latest.pc) * 100 : null);
  const isUp = (chgPct ?? chg ?? 0) >= 0;
  const changeColor = isUp ? "text-emerald-500" : "text-red-500";

  const chgStr = chg != null ? `${isUp ? "+" : ""}KES ${chg.toFixed(2)}` : "—";
  const chgPctStr = chgPct != null ? `${isUp ? "+" : ""}${chgPct.toFixed(2)}%` : "—";

  if (compact) {
    return (
      <div className="rounded-xl border border-rim bg-surface px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Market Quote</p>
          <span className="font-mono text-[10px] text-hint">{latest.date}</span>
        </div>
        <div>
          <MetricRow label="Open"       value={fmtKES(latest.o)} />
          <MetricRow label="High"       value={fmtKES(latest.h)} accent="text-emerald-500" />
          <MetricRow label="Low"        value={fmtKES(latest.l)} accent="text-red-500" />
          <MetricRow label="Close"      value={fmtKES(close)} />
          <MetricRow label="Prev Close" value={fmtKES(latest.pc)} />
          <MetricRow label="Change"     value={chgStr}    accent={changeColor} />
          <MetricRow label="Change %"   value={chgPctStr} accent={changeColor} />
          <MetricRow label="Volume"     value={fmtVol(latest.v)} />
          {latest.vv != null && (
            <MetricRow label="Value Traded" value={`KES ${fmtVol(latest.vv)}`} />
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface px-5 py-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Market Quote
        </p>
        <span className="font-mono text-[10px] text-hint">{latest.date}</span>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8">
        <Metric label="Open"       value={fmtKES(latest.o)} />
        <Metric label="High"       value={fmtKES(latest.h)} accent="text-emerald-500" />
        <Metric label="Low"        value={fmtKES(latest.l)} accent="text-red-500" />
        <Metric label="Close"      value={fmtKES(close)} />
        <Metric label="Prev Close" value={fmtKES(latest.pc)} />
        <Metric label="Change"     value={chgStr}    accent={changeColor} />
        <Metric label="Change %"   value={chgPctStr} accent={changeColor} />
        <Metric label="Volume"     value={fmtVol(latest.v)} />
      </div>

      {latest.vv != null && (
        <div className="mt-2 grid grid-cols-1">
          <Metric label="Value Traded" value={`KES ${fmtVol(latest.vv)}`} />
        </div>
      )}
    </div>
  );
};
