import type { FC } from "react";
import type { MarketOverviewDoc, CompanyDoc } from "../../types";

type Props = {
  market: MarketOverviewDoc;
  companies: CompanyDoc[];
};

const EAT_TZ = "Africa/Nairobi";

// Return the newest price_updated_at among companies whose latest push came
// from a live intraday tier, plus how many such tickers there are. Null if
// no company is currently marked live.
function computeLiveFreshness(companies: CompanyDoc[]): {
  latestIso: string;
  liveCount: number;
} | null {
  let latest: string | null = null;
  let n = 0;
  for (const c of companies) {
    if (c.price_is_live !== true) continue;
    const ts = c.price_updated_at;
    if (!ts) continue;
    n += 1;
    if (!latest || ts > latest) latest = ts;
  }
  if (!latest || n === 0) return null;
  return { latestIso: latest, liveCount: n };
}

export const MarketSummaryStrip: FC<Props> = ({ market, companies }) => {
  const nseVal = market.nse20_value != null ? market.nse20_value.toFixed(2) : "N/A";
  const nsePct = market.nse20_change_pct;
  const { BUY, HOLD, SELL } = market.signal_distribution;

  const live = computeLiveFreshness(companies);
  const liveTime = live
    ? new Date(live.latestIso).toLocaleTimeString("en-KE", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone: EAT_TZ,
      })
    : null;

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
      {live && liveTime ? (
        <span
          title={`${live.liveCount} tickers updated from live NSE feed — ~15 minute delay`}
          className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-400"
        >
          <span className="relative inline-flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
          </span>
          Live · {liveTime} EAT
          <span className="text-emerald-500/70">· 15 min delayed</span>
        </span>
      ) : (
        market.date && <span className="text-xs text-hint">as of {market.date}</span>
      )}
    </div>
  );
};
