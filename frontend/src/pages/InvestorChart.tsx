import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import { useCompany, useLatestTechnicals } from "../hooks/useCompany";
import { useHistoricalPrices } from "../hooks/useHistoricalPrices";
import { useWatchlist } from "../hooks/useWatchlist";
import { CompanyLogo } from "../components/ui/CompanyLogo";
import { LeftWatchlistRail } from "../components/layout/LeftWatchlistRail";
import { TimeframeTabs } from "../components/ui/TimeframeTabs";
import { FocusedPriceChart } from "../components/investor/FocusedPriceChart";
import { QuickCompareRow } from "../components/investor/QuickCompareRow";
import { cleanTicker, FETCH_START, todayIso, type TimeframeKey } from "../lib/timeframe";
import type { RtdbPricePoint } from "../hooks/useHistoricalPrices";

const StarIcon = ({ filled }: { filled?: boolean }) => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

const ExtLinkIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </svg>
);

function filterByTimeframeRtdb(points: RtdbPricePoint[], tf: TimeframeKey): RtdbPricePoint[] {
  if (!points.length) return points;
  if (tf === "Max") return points;
  if (tf === "YTD") {
    const cut = `${new Date().getFullYear()}-01-01`;
    return points.filter((p) => p.date >= cut);
  }
  const daysMap: Record<TimeframeKey, number> = {
    "1D": 1,
    "5D": 5,
    "1M": 30,
    "3M": 90,
    YTD: 0,
    "1Y": 365,
    "3Y": 1095,
    "5Y": 1825,
    Max: 0,
  };
  const days = daysMap[tf];
  if (tf === "1D") return points.slice(-1);
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  const iso = cutoff.toISOString().slice(0, 10);
  return points.filter((p) => p.date >= iso);
}

export const InvestorChart = () => {
  const { ticker: rawTicker = "" } = useParams<{ ticker: string }>();
  const ticker = rawTicker.toUpperCase();
  const cleaned = cleanTicker(ticker);
  const pushRecent = useRecentTickers((s) => s.push);

  const [timeframe, setTimeframe] = useState<TimeframeKey>("1M");

  useEffect(() => {
    if (ticker) pushRecent(ticker);
  }, [ticker, pushRecent]);

  const { data: company } = useCompany(ticker);
  const { data: technicals } = useLatestTechnicals(ticker);
  const { data: rtdbPrices = [] } = useHistoricalPrices(cleaned, FETCH_START, todayIso());

  const visible = useMemo(() => filterByTimeframeRtdb(rtdbPrices, timeframe), [rtdbPrices, timeframe]);

  const latestRow = rtdbPrices.length > 0 ? rtdbPrices[rtdbPrices.length - 1] : null;
  const previousClose = latestRow?.pc ?? null;
  const currentPrice = company?.current_price ?? latestRow?.c ?? null;
  const changePct = company?.change_pct_today ?? latestRow?.pch ?? null;
  const changeAbs =
    currentPrice != null && previousClose != null ? currentPrice - previousClose : null;
  const up = changePct != null && changePct >= 0;
  const trendColor = changePct == null ? "text-hint" : up ? "text-emerald-500" : "text-red-500";

  const { isAuthenticated, has, add, remove, isPending } = useWatchlist();
  const isWatched = has(ticker);

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8">
      <div className="grid gap-3 lg:grid-cols-[240px_minmax(0,1fr)]">
        <LeftWatchlistRail />

        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rim bg-surface px-4 py-3">
            <div className="flex items-center gap-3">
              {company && (
                <CompanyLogo
                  id={ticker}
                  short={company.short}
                  color={company.color}
                  icon={company.icon}
                  size="lg"
                />
              )}
              <div>
                <div className="flex items-center gap-1.5">
                  <h1 className="text-base font-bold text-ink">
                    {company?.name ?? ticker}
                  </h1>
                  <span className="font-mono text-xs text-muted">({ticker})</span>
                  <a
                    href={`/dashboard/${ticker}`}
                    className="text-hint transition-colors hover:text-ink"
                    title="Open overview"
                    aria-label="Open overview"
                  >
                    <ExtLinkIcon />
                  </a>
                </div>
                <p className="text-[10px] uppercase tracking-wider text-hint">
                  NAIROBI SECURITIES EXCHANGE
                  {company?.sector && <> · {company.sector}</>}
                </p>
              </div>
              <button
                type="button"
                disabled={!isAuthenticated || isPending}
                title={
                  !isAuthenticated
                    ? "Sign in to add to watchlist"
                    : isWatched
                    ? `Remove ${ticker} from watchlist`
                    : `Add ${ticker} to watchlist`
                }
                onClick={() => (isWatched ? remove(ticker) : add(ticker))}
                className={`ml-2 flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-semibold transition-colors ${
                  isAuthenticated && isWatched
                    ? "border-accent bg-accent/10 text-accent"
                    : !isAuthenticated
                    ? "cursor-not-allowed border-seam bg-raised/50 text-hint"
                    : "border-rim bg-raised text-ink hover:bg-raised/70"
                }`}
              >
                <StarIcon filled={isWatched} />
                <span>{isWatched ? "Watching" : "Watchlist"}</span>
              </button>
            </div>

            <div className="flex items-baseline gap-2">
              {currentPrice != null ? (
                <>
                  <span className="font-mono text-2xl font-black text-ink">
                    KES {currentPrice.toFixed(2)}
                  </span>
                  {changeAbs != null && changePct != null && (
                    <span className={`font-mono text-sm font-semibold ${trendColor}`}>
                      {up ? "+" : "−"}
                      {Math.abs(changeAbs).toFixed(2)} ({up ? "+" : "−"}
                      {Math.abs(changePct).toFixed(2)}%)
                    </span>
                  )}
                  <span className="ml-2 text-[10px] uppercase tracking-wider text-hint">
                    24H CHANGE
                  </span>
                  {(company?.price_date ?? latestRow?.date) && (
                    <span className="text-[10px] text-hint">
                      · {company?.price_date ?? latestRow?.date}
                    </span>
                  )}
                </>
              ) : (
                <span className="text-xl text-hint">—</span>
              )}
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-rim bg-surface">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-2.5">
              <TimeframeTabs value={timeframe} onChange={setTimeframe} />
              <div className="flex items-center gap-1.5">
                <span
                  className="rounded border border-seam bg-raised/60 px-2 py-1 text-[10px] font-semibold text-hint"
                  title="Chart type — coming soon"
                >
                  Area
                </span>
                <span
                  className="rounded border border-seam bg-raised/60 px-2 py-1 text-[10px] font-semibold text-hint"
                  title="Candles — coming soon"
                >
                  Candles
                </span>
                <span
                  className="rounded border border-seam bg-raised/60 px-2 py-1 text-[10px] font-semibold text-hint"
                  title="Indicators overlay — coming soon"
                >
                  Indicators
                </span>
              </div>
            </div>

            <div className="border-b border-seam px-4 py-2">
              <QuickCompareRow ticker={ticker} sector={company?.sector ?? null} />
            </div>

            <div className="px-2 py-2">
              <FocusedPriceChart data={visible} color={company?.color ?? "rgb(var(--accent))"} />
              {visible.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-2 text-[10px] text-hint">
                  <span>
                    {visible[0].date} → {visible[visible.length - 1].date} · {visible.length}{" "}
                    trading {visible.length === 1 ? "day" : "days"}
                  </span>
                  <span className="flex items-center gap-3">
                    {technicals?.avg_volume_30d != null && (
                      <span>
                        Avg Vol 30d:{" "}
                        <span className="font-mono text-muted">
                          {(technicals.avg_volume_30d / 1_000_000).toFixed(2)}M
                        </span>
                      </span>
                    )}
                    <Link
                      to={`/dashboard/${ticker}`}
                      className="rounded border border-seam px-1.5 py-0.5 font-medium transition-colors hover:border-rim hover:text-ink"
                    >
                      Overview →
                    </Link>
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
