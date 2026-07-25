import type { FC } from "react";
import type { MarketOverviewDoc, CompanyDoc } from "../../types";

type Props = {
  market: MarketOverviewDoc;
  companies: CompanyDoc[];
};

export const MarketSummaryStrip: FC<Props> = ({ market, companies }) => {
  const nseVal = market.nse20_value != null ? market.nse20_value.toFixed(2) : "N/A";
  const nsePct = market.nse20_change_pct;
  const { BUY, HOLD, SELL } = market.signal_distribution;

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-rim bg-surface px-5 py-3">
      <div className="flex items-center gap-2 rounded-lg border border-seam bg-canvas px-3 py-1.5">
        <span className="text-xs font-semibold text-muted">NSE 20</span>
        <span className="font-mono text-sm font-bold text-ink">{nseVal}</span>
        {nsePct != null && (
          <span className={`font-mono text-xs font-semibold ${nsePct >= 0 ? "text-emerald-500" : "text-red-500"}`}>
            {nsePct >= 0 ? "+" : ""}{nsePct.toFixed(2)}%
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-400">
          {BUY} BUY
        </span>
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-400">
          {HOLD} HOLD
        </span>
        <span className="rounded-full border border-red-500/30 bg-red-500/10 px-3 py-1 text-xs font-semibold text-red-400">
          {SELL} SELL
        </span>
      </div>

      <span className="text-xs text-muted">{companies.length} securities tracked</span>
      {market.date && <span className="text-xs text-hint">as of {market.date}</span>}
    </div>
  );
};
