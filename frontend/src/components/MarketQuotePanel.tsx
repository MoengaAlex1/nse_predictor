import type { FC } from "react";
import type { RtdbPricePoint } from "../hooks/useHistoricalPrices";

interface Props {
  latest: RtdbPricePoint | null;
  currentPrice?: number | null;
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

const Metric: FC<{ label: string; value: string; accent?: string }> = ({ label, value, accent }) => (
  <div className="rounded-lg border border-seam bg-raised/50 p-3">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</p>
    <p className={`mt-0.5 font-mono text-sm font-semibold ${accent ?? "text-ink"}`}>{value}</p>
  </div>
);

export const MarketQuotePanel: FC<Props> = ({ latest, currentPrice }) => {
  if (!latest) return null;

  const close = latest.c ?? currentPrice ?? null;
  const chg = latest.ch ?? (close != null && latest.pc != null ? close - latest.pc : null);
  const chgPct = latest.pch ?? (chg != null && latest.pc && latest.pc > 0 ? (chg / latest.pc) * 100 : null);
  const isUp = (chgPct ?? chg ?? 0) >= 0;
  const changeColor = isUp ? "text-emerald-500" : "text-red-500";

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface px-5 py-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Market Quote
        </p>
        <span className="font-mono text-[10px] text-hint">{latest.date}</span>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8">
        <Metric label="Open"  value={fmtKES(latest.o)} />
        <Metric label="High"  value={fmtKES(latest.h)} accent="text-emerald-500" />
        <Metric label="Low"   value={fmtKES(latest.l)} accent="text-red-500" />
        <Metric label="Close" value={fmtKES(close)} />
        <Metric label="Prev Close" value={fmtKES(latest.pc)} />
        <Metric
          label="Change"
          value={chg != null ? `${isUp ? "+" : ""}KES ${chg.toFixed(2)}` : "—"}
          accent={changeColor}
        />
        <Metric
          label="Change %"
          value={chgPct != null ? `${isUp ? "+" : ""}${chgPct.toFixed(2)}%` : "—"}
          accent={changeColor}
        />
        <Metric label="Volume" value={fmtVol(latest.v)} />
      </div>

      {latest.vv != null && (
        <div className="mt-2 grid grid-cols-1">
          <Metric label="Value Traded" value={`KES ${fmtVol(latest.vv)}`} />
        </div>
      )}
    </div>
  );
};
