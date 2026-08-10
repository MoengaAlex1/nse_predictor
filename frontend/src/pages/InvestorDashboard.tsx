import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import { useCompany, useLatestTechnicals, useFundamentals } from "../hooks/useCompany";
import { useHistoricalPrices } from "../hooks/useHistoricalPrices";
import { PriceHeader } from "../components/investor/PriceHeader";
import { PriceAreaChart } from "../components/investor/PriceAreaChart";
import { TimeframeTabs } from "../components/ui/TimeframeTabs";
import { RightStatsRail } from "../components/layout/RightStatsRail";
import {
  cleanTicker,
  filterByTimeframe,
  FETCH_START,
  todayIso,
  type TimeframeKey,
} from "../lib/timeframe";
import type { PricePoint } from "../types";

const PlaceholderBlock = ({ label, height }: { label: string; height: string }) => (
  <div
    className={`flex ${height} items-center justify-center rounded-lg border border-dashed border-seam bg-surface/40 text-xs text-hint`}
  >
    {label}
  </div>
);

export const InvestorDashboard = () => {
  const { ticker: rawTicker = "" } = useParams<{ ticker: string }>();
  const ticker = rawTicker.toUpperCase();
  const cleaned = cleanTicker(ticker);
  const pushRecent = useRecentTickers((s) => s.push);

  const [timeframe, setTimeframe] = useState<TimeframeKey>("3M");

  useEffect(() => {
    if (ticker) pushRecent(ticker);
  }, [ticker, pushRecent]);

  const { data: company } = useCompany(ticker);
  const { data: technicals } = useLatestTechnicals(ticker);
  const { data: fundamentals } = useFundamentals(ticker);
  const { data: rtdbPrices = [] } = useHistoricalPrices(cleaned, FETCH_START, todayIso());

  const history: PricePoint[] = useMemo(
    () =>
      rtdbPrices
        .filter((p) => p.c != null)
        .map((p) => ({ date: p.date, price: p.c as number })),
    [rtdbPrices],
  );

  const visible = useMemo(() => filterByTimeframe(history, timeframe), [history, timeframe]);

  const latestRow = rtdbPrices.length > 0 ? rtdbPrices[rtdbPrices.length - 1] : null;
  const previousClose = latestRow?.pc ?? null;
  const dayLow = latestRow?.l ?? null;
  const dayHigh = latestRow?.h ?? null;

  const currentPrice = company?.current_price ?? latestRow?.c ?? null;
  const changePct = company?.change_pct_today ?? latestRow?.pch ?? null;
  const changeAbs =
    currentPrice != null && previousClose != null ? currentPrice - previousClose : null;

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8">
      <div className="grid gap-3 lg:grid-cols-[240px_minmax(0,1fr)_320px]">
        <PlaceholderBlock label="Left rail — Watchlist + Suggested (Phase C)" height="h-[560px]" />

        <div className="flex flex-col gap-3">
          <PriceHeader
            company={company}
            ticker={ticker}
            currentPrice={currentPrice}
            changeAbs={changeAbs}
            changePct={changePct}
            priceAsOf={company?.price_date ?? latestRow?.date ?? null}
          />

          <div className="overflow-hidden rounded-xl border border-rim bg-surface">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-muted">
                  Price
                </span>
                {visible.length > 0 && (
                  <span className="ml-2 font-mono text-[10px] text-hint">
                    {visible[0].date} → {visible[visible.length - 1].date} · {visible.length}{" "}
                    {visible.length === 1 ? "day" : "days"}
                  </span>
                )}
              </div>
              <TimeframeTabs value={timeframe} onChange={setTimeframe} />
            </div>
            <div className="px-1 pb-3 pt-1">
              <PriceAreaChart data={visible} color={company?.color ?? "rgb(var(--accent))"} />
            </div>
          </div>

          <PlaceholderBlock label="Quick Compare row (Phase C)" height="h-16" />
          <div className="grid gap-3 md:grid-cols-2">
            <PlaceholderBlock label="AI Insights (Phase D)" height="h-48" />
            <PlaceholderBlock label="Score Radar (Phase D)" height="h-48" />
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <PlaceholderBlock label="Analyst" height="h-28" />
            <PlaceholderBlock label="Model Target" height="h-28" />
            <PlaceholderBlock label="Earnings" height="h-28" />
            <PlaceholderBlock label="Financials" height="h-28" />
            <PlaceholderBlock label="Trading" height="h-28" />
            <PlaceholderBlock label="Profitability" height="h-28" />
          </div>
        </div>

        <RightStatsRail
          company={company}
          technicals={technicals}
          fundamentals={fundamentals}
          dayLow={dayLow}
          dayHigh={dayHigh}
          previousClose={previousClose}
        />
      </div>
    </div>
  );
};
