import type { FC } from "react";
import { fmtCompact, fmtPrice, EM_DASH } from "../../lib/format";
import type { TechnicalsDoc } from "../../types";

type TradingCardProps = {
  technicals: TechnicalsDoc | null | undefined;
  dayLow: number | null;
  dayHigh: number | null;
};

const Row: FC<{ label: string; value: string; muted: boolean }> = ({ label, value, muted }) => (
  <div className="flex items-baseline justify-between gap-2 py-0.5">
    <span className="text-[11px] text-muted">{label}</span>
    <span
      className={`shrink-0 font-mono text-xs tabular-nums ${muted ? "text-hint" : "font-semibold text-ink"}`}
    >
      {value}
    </span>
  </div>
);

export const TradingCard: FC<TradingCardProps> = ({ technicals, dayLow, dayHigh }) => {
  const dayRange =
    dayLow != null && dayHigh != null ? `${fmtPrice(dayLow)} – ${fmtPrice(dayHigh)}` : EM_DASH;

  return (
    <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted">Trading</p>
      <div className="flex flex-1 flex-col justify-center gap-0.5">
        <Row
          label="Avg Volume 30d"
          value={fmtCompact(technicals?.avg_volume_30d)}
          muted={technicals?.avg_volume_30d == null}
        />
        <Row
          label="Volatility 30d"
          value={technicals?.volatility_30d != null ? `${technicals.volatility_30d.toFixed(2)}%` : EM_DASH}
          muted={technicals?.volatility_30d == null}
        />
        <Row label="Day Range" value={dayRange} muted={dayLow == null || dayHigh == null} />
      </div>
    </div>
  );
};
