import type { FC } from "react";
import type { TechnicalsDoc } from "../../types";

const fmtVolume = (v: number | null | undefined): string => {
  if (v == null) return "—";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString();
};

type TradingCardProps = {
  technicals: TechnicalsDoc | null | undefined;
  dayLow: number | null;
  dayHigh: number | null;
};

export const TradingCard: FC<TradingCardProps> = ({ technicals, dayLow, dayHigh }) => (
  <div className="rounded-xl border border-rim bg-surface p-3">
    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted">Trading</p>
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] text-muted">Avg Volume 30d</span>
        <span
          className={`font-mono text-xs ${technicals?.avg_volume_30d != null ? "font-semibold text-ink" : "text-hint"}`}
        >
          {fmtVolume(technicals?.avg_volume_30d)}
        </span>
      </div>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] text-muted">Volatility 30d</span>
        <span
          className={`font-mono text-xs ${technicals?.volatility_30d != null ? "font-semibold text-ink" : "text-hint"}`}
        >
          {technicals?.volatility_30d != null ? `${technicals.volatility_30d.toFixed(2)}%` : "—"}
        </span>
      </div>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] text-muted">Day Range</span>
        <span
          className={`font-mono text-xs ${dayLow != null && dayHigh != null ? "font-semibold text-ink" : "text-hint"}`}
        >
          {dayLow != null && dayHigh != null ? `${dayLow.toFixed(2)} – ${dayHigh.toFixed(2)}` : "—"}
        </span>
      </div>
    </div>
  </div>
);
