import type { FC } from "react";
import { Link } from "react-router-dom";
import { useRecentTickers } from "../../hooks/useRecentTickers";
import { useCompanies } from "../../hooks/useCompanies";
import { useMarketOverview } from "../../hooks/useMarket";
import { fmtPct, fmtPrice, arrow, trendClass } from "../../lib/format";
import type { CompanyDoc } from "../../types";

type ChipProps = {
  ticker: string;
  meta?: CompanyDoc;
  pct?: number;
};

const Chip: FC<ChipProps> = ({ ticker, meta, pct }) => {
  const up = pct != null && pct >= 0;
  return (
    <Link
      to={`/chart/${ticker}`}
      className="flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-seam bg-raised/50 px-2.5 text-xs transition-colors hover:border-rim hover:bg-raised"
    >
      <span className="font-semibold text-ink">{ticker}</span>
      {meta?.short && meta.short !== ticker && (
        <span className="hidden text-hint md:inline">{meta.short}</span>
      )}
      {pct != null && (
        <span className={`font-mono tabular-nums ${trendClass(pct)}`}>
          {arrow(up)} {fmtPct(pct)}
        </span>
      )}
    </Link>
  );
};

const IndexPill: FC<{ label: string; value?: number | null; pct?: number | null }> = ({ label, value, pct }) => {
  const up = pct != null && pct >= 0;
  return (
    <div className="flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-seam bg-raised/50 px-2.5 text-xs">
      <span className="font-semibold text-muted">{label}</span>
      {value != null && <span className="font-mono tabular-nums text-ink">{fmtPrice(value)}</span>}
      {pct != null && (
        <span className={`font-mono tabular-nums ${trendClass(pct)}`}>
          {arrow(up)} {fmtPct(pct)}
        </span>
      )}
    </div>
  );
};

export const RecentTickersStrip: FC = () => {
  const recents = useRecentTickers((s) => s.tickers);
  const { data: companies = [] } = useCompanies();
  const { data: market } = useMarketOverview();

  const companyMap = new Map(companies.map((c) => [c.ticker, c]));

  const suggestedSeed = market
    ? [
        ...market.top_gainers.slice(0, 4).map((g) => ({ ticker: g.ticker, pct: g.change_pct })),
        ...market.top_losers.slice(0, 3).map((l) => ({ ticker: l.ticker, pct: l.change_pct })),
      ]
    : [];

  const suggested = suggestedSeed.filter((s) => !recents.includes(s.ticker));

  return (
    <div className="sticky top-[88px] z-30 h-9 border-b border-seam bg-canvas/95 backdrop-blur">
      <div className="mx-auto flex h-full max-w-[1600px] items-center gap-2 overflow-x-auto scrollbar-none px-4 sm:px-6 lg:px-8">
        <span className="shrink-0 text-[11px] font-semibold uppercase tracking-wider text-hint">
          {recents.length > 0 ? "Recent" : "Suggested"}
        </span>

        {recents.length > 0 &&
          recents.map((t) => <Chip key={`r-${t}`} ticker={t} meta={companyMap.get(t)} />)}

        {recents.length > 0 && suggested.length > 0 && (
          <span className="h-4 w-px shrink-0 bg-seam" aria-hidden="true" />
        )}

        {market?.nse20_value != null && (
          <IndexPill label="NSE 20" value={market.nse20_value} pct={market.nse20_change_pct} />
        )}

        {suggested.slice(0, 6).map((s) => (
          <Chip key={`s-${s.ticker}`} ticker={s.ticker} meta={companyMap.get(s.ticker)} pct={s.pct} />
        ))}
      </div>
    </div>
  );
};
