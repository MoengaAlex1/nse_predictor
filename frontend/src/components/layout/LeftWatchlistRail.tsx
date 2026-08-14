import type { FC } from "react";
import { Link } from "react-router-dom";
import { CompanyLogo } from "../ui/CompanyLogo";
import { useCompanies } from "../../hooks/useCompanies";
import { useWatchlist } from "../../hooks/useWatchlist";
import { useMarketOverview } from "../../hooks/useMarket";
import { fmtPrice, fmtPct, trendClass, EM_DASH } from "../../lib/format";
import { shortFromDisplayTicker } from "../../lib/identity";
import type { CompanyDoc } from "../../types";

// Tiny inline sparkline drawn from CompanyDoc.price_preview (7-day array
// already denormalised into the companies collection — no extra fetch).
const MiniSparkline: FC<{ points: number[]; up: boolean }> = ({ points, up }) => {
  if (!points || points.length < 2) return <span className="inline-block h-3 w-10" />;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const width = 40;
  const height = 12;
  const d = points
    .map((v, i) => {
      const x = (i / (points.length - 1)) * width;
      const y = height - ((v - min) / range) * height;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="shrink-0">
      <path d={d} fill="none" stroke={up ? "#22c55e" : "#ef4444"} strokeWidth="1.25" strokeLinecap="round" />
    </svg>
  );
};

type RowProps = {
  company: CompanyDoc;
};

const WatchlistRow: FC<RowProps> = ({ company }) => {
  const pct = company.change_pct_today;
  const up = pct != null && pct >= 0;
  return (
    <Link
      to={`/chart/${company.ticker}`}
      className="flex items-center gap-2 rounded-md px-2 py-1.5 transition-colors hover:bg-raised/60"
    >
      <CompanyLogo id={company.id} short={company.short} color={company.color} icon={company.icon} size="sm" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-semibold text-ink">{company.short}</p>
        <p className="truncate font-mono text-[10px] text-hint">{company.ticker}</p>
      </div>
      <MiniSparkline points={company.price_preview ?? []} up={up} />
      <div className="min-w-[56px] shrink-0 text-right">
        <p className="font-mono text-xs font-semibold text-ink tabular-nums">
          {company.current_price != null ? fmtPrice(company.current_price) : EM_DASH}
        </p>
        <p className={`font-mono text-[10px] tabular-nums ${trendClass(pct)}`}>
          {pct != null ? fmtPct(pct) : EM_DASH}
        </p>
      </div>
    </Link>
  );
};

export const LeftWatchlistRail: FC = () => {
  const { data: companies = [] } = useCompanies();
  const { tickers: watchlistTickers, isAuthenticated } = useWatchlist();
  const { data: market } = useMarketOverview();

  // Post primary-key refactor: companyMap keys are always the short form
  // (c.id === c.short). Watchlist entries stored in legacy "SCOM.NR" form
  // get coerced by shortFromDisplayTicker() so old bookmarks still resolve.
  const companyMap = new Map(companies.map((c) => [c.id, c]));
  const watchlist = watchlistTickers
    .map((t) => companyMap.get(shortFromDisplayTicker(t)))
    .filter((c): c is CompanyDoc => !!c);

  const suggestedTickers = market
    ? [
        ...market.top_gainers.slice(0, 4).map((g) => g.ticker),
        ...market.top_losers.slice(0, 3).map((l) => l.ticker),
      ]
    : [];
  const watchlistIds = new Set(watchlistTickers.map((t) => shortFromDisplayTicker(t)));
  const suggested = suggestedTickers
    .filter((t) => !watchlistIds.has(shortFromDisplayTicker(t)))
    .map((t) => companyMap.get(shortFromDisplayTicker(t)))
    .filter((c): c is CompanyDoc => !!c)
    .slice(0, 6);

  return (
    <aside className="hidden lg:flex flex-col gap-4 rounded-xl border border-rim bg-surface p-3">
      <section>
        <div className="mb-2 flex items-baseline justify-between px-1">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            My Watchlist
          </h2>
          {isAuthenticated && watchlist.length > 0 && (
            <span className="font-mono text-[10px] tabular-nums text-hint">{watchlist.length}</span>
          )}
        </div>
        {!isAuthenticated ? (
          <p className="px-2 py-3 text-[11px] leading-relaxed text-hint">
            Sign in to save tickers to your watchlist.
          </p>
        ) : watchlist.length === 0 ? (
          <p className="px-2 py-3 text-[11px] leading-relaxed text-hint">
            No tickers yet. Open a dashboard and hit the star icon to add one.
          </p>
        ) : (
          <div className="flex flex-col gap-0.5">
            {watchlist.map((c) => (
              <WatchlistRow key={c.ticker} company={c} />
            ))}
          </div>
        )}
      </section>

      <section>
        <div className="mb-2 px-1">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            Suggested for you
          </h2>
        </div>
        {suggested.length === 0 ? (
          <p className="px-2 py-3 text-[11px] text-hint">Loading market data…</p>
        ) : (
          <div className="flex flex-col gap-0.5">
            {suggested.map((c) => (
              <WatchlistRow key={c.ticker} company={c} />
            ))}
          </div>
        )}
      </section>
    </aside>
  );
};
