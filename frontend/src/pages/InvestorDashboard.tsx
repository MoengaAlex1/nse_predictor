import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import { useCompany, useLatestTechnicals, useLatestSnapshot, useFundamentals, useFinancials as useFinancialsDoc } from "../hooks/useCompany";
import { useHistoricalPrices } from "../hooks/useHistoricalPrices";
import { PriceHeader } from "../components/investor/PriceHeader";
import { PriceAreaChart } from "../components/investor/PriceAreaChart";
import { QuickCompareRow } from "../components/investor/QuickCompareRow";
import { AIInsightsPanel } from "../components/investor/AIInsightsPanel";
import { ScoreRadarPanel } from "../components/investor/ScoreRadarPanel";
import { AnalystGaugeCard } from "../components/investor/AnalystGaugeCard";
import { ModelTargetCard } from "../components/investor/ModelTargetCard";
import { EarningsForecastCard } from "../components/investor/EarningsForecastCard";
import { FinancialsValuationCard } from "../components/investor/FinancialsValuationCard";
import { TradingCard } from "../components/investor/TradingCard";
import { ProfitabilityCard } from "../components/investor/ProfitabilityCard";
import { FilingsPanel } from "../components/investor/FilingsPanel";
import { AnnualFinancialsTable } from "../components/investor/AnnualFinancialsTable";
import { DividendHistoryChart } from "../components/investor/DividendHistoryChart";
import { DividendYieldTimeline } from "../components/investor/DividendYieldTimeline";
import { CorporateActionsTimeline } from "../components/investor/CorporateActionsTimeline";
import { ExDateCalendarStrip } from "../components/investor/ExDateCalendarStrip";
import { DividendSummaryCard } from "../components/investor/DividendSummaryCard";
import { UpcomingEventsCard } from "../components/investor/UpcomingEventsCard";
import { TimeframeTabs } from "../components/ui/TimeframeTabs";
import { RightStatsRail } from "../components/layout/RightStatsRail";
import { LeftWatchlistRail } from "../components/layout/LeftWatchlistRail";
import {
  cleanTicker,
  filterByTimeframe,
  FETCH_START,
  todayIso,
  type TimeframeKey,
} from "../lib/timeframe";
import type { PricePoint } from "../types";

export const InvestorDashboard = () => {
  const { ticker: rawTicker = "" } = useParams<{ ticker: string }>();
  const ticker = rawTicker.toUpperCase();
  const cleaned = cleanTicker(ticker);
  const pushRecent = useRecentTickers((s) => s.push);

  const [timeframe, setTimeframe] = useState<TimeframeKey>("3M");

  useEffect(() => {
    if (ticker) pushRecent(ticker);
  }, [ticker, pushRecent]);

  // Firestore doc ids are the "safe" ticker form — without .NR/.KE suffix
  // (paths can be edge-case fragile with dots). RTDB uses the same clean
  // form. Some entry points navigate here with the display ticker (SCOM.NR)
  // and some with the doc id (SCOM), so we normalize once and use the
  // cleaned form for every Firestore + RTDB fetch.
  const { data: company } = useCompany(cleaned);
  const { data: technicals } = useLatestTechnicals(cleaned);
  const { data: snapshot } = useLatestSnapshot(cleaned);
  const { data: fundamentals } = useFundamentals(cleaned);
  const { data: financials } = useFinancialsDoc(cleaned);
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
        <LeftWatchlistRail />

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

          <QuickCompareRow ticker={ticker} sector={company?.sector ?? null} />

          <div className="grid gap-3 md:grid-cols-2">
            <AIInsightsPanel
              technicals={technicals}
              snapshot={snapshot}
              currentPrice={currentPrice}
            />
            <ScoreRadarPanel />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <AnalystGaugeCard />
            <ModelTargetCard />
            <EarningsForecastCard />
            <FinancialsValuationCard />
            <TradingCard technicals={technicals} dayLow={dayLow} dayHigh={dayHigh} />
            <ProfitabilityCard />
          </div>

          {/* ── Financials & Corporate Actions ─────────────────────────────
              Populated by pipeline/scripts/extract_from_pdfs_ai.py,
              scrape_nse_daily_bulletins.py, and refresh_nse_disclosures.py.
              All three write into financials/{ticker} — this section is where
              that data becomes user-facing (previously locked behind
              FilingsPanel + a tiny slice of ValuationPanel).
          */}
          <div id="financials" className="pt-1">
            <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
              Financials & Corporate Actions
            </h2>
            <div className="flex flex-col gap-3">
              <AnnualFinancialsTable financials={financials} />

              <div className="grid gap-3 md:grid-cols-2">
                <DividendHistoryChart financials={financials} />
                <DividendYieldTimeline financials={financials} priceHistory={history} />
              </div>

              <ExDateCalendarStrip financials={financials} />

              <div className="grid gap-3 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
                <CorporateActionsTimeline financials={financials} />
                <div className="flex flex-col gap-3">
                  <DividendSummaryCard financials={financials} currentPrice={currentPrice} />
                  <UpcomingEventsCard financials={financials} />
                </div>
              </div>

              <FilingsPanel financials={financials} />
            </div>
          </div>
        </div>

        <RightStatsRail
          company={company}
          technicals={technicals}
          fundamentals={fundamentals}
          financials={financials}
          dayLow={dayLow}
          dayHigh={dayHigh}
          previousClose={previousClose}
        />
      </div>
    </div>
  );
};
