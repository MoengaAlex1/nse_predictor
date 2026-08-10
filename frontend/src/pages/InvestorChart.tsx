import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import { useCompany, useLatestTechnicals } from "../hooks/useCompany";
import { useCompanies } from "../hooks/useCompanies";
import { useHistoricalPrices } from "../hooks/useHistoricalPrices";
import { useWatchlist } from "../hooks/useWatchlist";
import { usePeers } from "../hooks/usePeers";
import { CompanyLogo } from "../components/ui/CompanyLogo";
import { LeftWatchlistRail } from "../components/layout/LeftWatchlistRail";
import { TimeframeTabs } from "../components/ui/TimeframeTabs";
import { FocusedPriceChart } from "../components/investor/FocusedPriceChart";
import {
  cleanTicker,
  FETCH_START,
  todayIso,
  type TimeframeKey,
} from "../lib/timeframe";
import {
  fmtKes,
  fmtChangeSigned,
  fmtPct,
  fmtCompact,
  fmtPrice,
  arrow,
  trendClass,
  EM_DASH,
} from "../lib/format";
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
  const [chartType, setChartType] = useState<"area" | "candles" | "indicators">("area");

  useEffect(() => {
    if (ticker) pushRecent(ticker);
  }, [ticker, pushRecent]);

  const { data: company } = useCompany(ticker);
  const { data: technicals } = useLatestTechnicals(ticker);
  const { data: allCompanies = [] } = useCompanies();
  const { data: rtdbPrices = [] } = useHistoricalPrices(cleaned, FETCH_START, todayIso());
  const peers = usePeers(ticker, company?.sector ?? null, 4);

  const visible = useMemo(
    () => filterByTimeframeRtdb(rtdbPrices, timeframe),
    [rtdbPrices, timeframe],
  );

  const latestRow = rtdbPrices.length > 0 ? rtdbPrices[rtdbPrices.length - 1] : null;
  const previousClose = latestRow?.pc ?? null;
  const currentPrice = company?.current_price ?? latestRow?.c ?? null;
  const changePct = company?.change_pct_today ?? latestRow?.pch ?? null;
  const changeAbs =
    currentPrice != null && previousClose != null ? currentPrice - previousClose : null;
  const up = changePct != null && changePct >= 0;
  const trendColor = trendClass(changePct);

  const { isAuthenticated, has, add, remove, isPending } = useWatchlist();
  const isWatched = has(ticker);

  // Guard against silent stat mismatches: if the same ticker exists in the
  // companies collection, its short name and sector are the source of truth.
  const canonical = allCompanies.find((c) => c.ticker.toUpperCase() === ticker);
  const displayName = company?.name ?? canonical?.name ?? ticker;
  const displaySector = company?.sector ?? canonical?.sector ?? null;

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8">
      <div className="grid gap-3 lg:grid-cols-[240px_minmax(0,1fr)]">
        <LeftWatchlistRail />

        <div className="flex flex-col gap-3">
          {/* ── Ticker header ────────────────────────────────────────────── */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rim bg-surface px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              {company && (
                <CompanyLogo
                  id={ticker}
                  short={company.short}
                  color={company.color}
                  icon={company.icon}
                  size="lg"
                />
              )}
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <h1 className="truncate text-base font-bold text-ink">{displayName}</h1>
                  <span className="shrink-0 font-mono text-xs text-muted">({ticker})</span>
                  <Link
                    to={`/company/${ticker}`}
                    className="shrink-0 text-hint transition-colors hover:text-ink"
                    title="Open full report"
                    aria-label="Open full report"
                  >
                    <ExtLinkIcon />
                  </Link>
                </div>
                <p className="truncate text-[10px] uppercase tracking-wider text-hint">
                  Nairobi Securities Exchange
                  {displaySector && <> · {displaySector}</>}
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
                className={`ml-2 flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-semibold transition-colors ${
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

            <div className="flex shrink-0 items-baseline gap-x-2 gap-y-1">
              {currentPrice != null ? (
                <>
                  <span className="font-mono text-2xl font-black text-ink tabular-nums">
                    {fmtKes(currentPrice)}
                  </span>
                  {changeAbs != null && changePct != null && (
                    <span className={`font-mono text-sm font-semibold tabular-nums ${trendColor}`}>
                      {arrow(up)} {fmtChangeSigned(changeAbs)} ({fmtPct(changePct)})
                    </span>
                  )}
                  <span className="ml-1 text-[10px] uppercase tracking-wider text-hint">
                    24H change
                  </span>
                  {(company?.price_date ?? latestRow?.date) && (
                    <span className="text-[10px] text-hint">
                      · {company?.price_date ?? latestRow?.date}
                    </span>
                  )}
                </>
              ) : (
                <span className="text-xl text-hint">{EM_DASH}</span>
              )}
            </div>
          </div>

          {/* ── Chart card ───────────────────────────────────────────────── */}
          <div className="overflow-hidden rounded-xl border border-rim bg-surface">
            {/* Timeframe + chart-type toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-2.5">
              <TimeframeTabs value={timeframe} onChange={setTimeframe} />
              <div className="flex items-center gap-0.5 rounded-lg border border-rim bg-raised p-0.5">
                {(["area", "candles", "indicators"] as const).map((k) => {
                  const active = chartType === k;
                  const supported = k === "area";
                  return (
                    <button
                      key={k}
                      type="button"
                      disabled={!supported}
                      onClick={() => supported && setChartType(k)}
                      title={supported ? undefined : `${k[0].toUpperCase()}${k.slice(1)} — coming soon`}
                      className={`rounded-md px-2 py-1 text-[10px] font-semibold transition-colors ${
                        active && supported
                          ? "bg-accent text-white dark:bg-accent/20 dark:text-accent"
                          : supported
                          ? "text-muted hover:text-ink"
                          : "cursor-not-allowed text-hint"
                      }`}
                    >
                      {k[0].toUpperCase() + k.slice(1)}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Compare-to inline strip */}
            {peers.length > 0 && (
              <div className="flex items-center gap-2 border-b border-seam px-4 py-2 overflow-x-auto scrollbar-none">
                <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wider text-hint">
                  Compare to
                </span>
                {peers.map((p) => {
                  const pct = p.change_pct_today;
                  const puUp = pct != null && pct >= 0;
                  return (
                    <Link
                      key={p.ticker}
                      to={`/chart/${p.ticker}`}
                      className="flex h-7 shrink-0 items-center gap-1.5 rounded-full border border-seam bg-raised/50 px-2.5 text-[11px] transition-colors hover:border-rim hover:bg-raised"
                    >
                      <span className="font-semibold text-ink">{p.short}</span>
                      {p.current_price != null && (
                        <span className="font-mono tabular-nums text-hint">
                          {fmtPrice(p.current_price)}
                        </span>
                      )}
                      {pct != null && (
                        <span className={`font-mono tabular-nums ${trendClass(pct)}`}>
                          {arrow(puUp)} {fmtPct(pct)}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            )}

            {/* Main chart */}
            <div className="px-2 py-2">
              <FocusedPriceChart
                data={visible}
                color={company?.color ?? "rgb(var(--accent))"}
                height={620}
              />
              {visible.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-2 text-[10px] text-hint">
                  <span className="font-mono tabular-nums">
                    {visible[0].date} → {visible[visible.length - 1].date} · {visible.length}{" "}
                    trading {visible.length === 1 ? "day" : "days"}
                  </span>
                  <span className="flex items-center gap-3">
                    {technicals?.avg_volume_30d != null && (
                      <span>
                        Avg Vol 30d:{" "}
                        <span className="font-mono tabular-nums text-muted">
                          {fmtCompact(technicals.avg_volume_30d)}
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
