import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import {
  useCompany,
  useFinancials as useFinancialsDoc,
  useFundamentals,
  useLatestSnapshot,
  useLatestTechnicals,
  useNews,
} from "../hooks/useCompany";
import { usePrices } from "../hooks/usePrices";
import { resolveDisplayPrice } from "../lib/format";
import { FilingsPanel } from "../components/investor/FilingsPanel";
import { ReturnsCalculator } from "../components/investor/ReturnsCalculator";
import { TradingWorkstation } from "../components/investor/TradingWorkstation";
import { PriceMoveBanner } from "../components/investor/PriceMoveBanner";
import { ValuationPanel } from "../components/investor/ValuationPanel";
import { AIInsightsPanel } from "../components/investor/AIInsightsPanel";
import { RadarScoreCard } from "../components/investor/RadarScoreCard";
import { NewsPanel } from "../components/investor/NewsPanel";
import { FinancialsPanel } from "../components/FinancialsPanel";
import { FinancialNarrativeCard } from "../components/FinancialNarrativeCard";
import { DeepAnalysisPanel } from "../components/DeepAnalysisPanel";
import { toBase } from "../lib/ticker";

// Single canonical company page. The old /company/{ticker} route now
// redirects here — the audit found users bounced between /company and
// /chart with no clear reason for the two views. This page keeps the
// TradingView-style workstation as the primary artefact and stacks the
// analysis cards (returns calculator, valuation, financials,
// AI insights, filings, news) below so nothing is lost in the merge.
export const InvestorChart = () => {
  const { ticker: rawTicker = "" } = useParams<{ ticker: string }>();
  const cleaned = toBase(rawTicker);
  const pushRecent = useRecentTickers((s) => s.push);

  useEffect(() => {
    if (cleaned) pushRecent(cleaned);
  }, [cleaned, pushRecent]);

  const { data: financials } = useFinancialsDoc(cleaned);
  const { data: company } = useCompany(cleaned);
  const { data: fundamentals } = useFundamentals(cleaned);
  const { data: snapshot } = useLatestSnapshot(cleaned);
  const { data: technicals } = useLatestTechnicals(cleaned);
  const { data: newsItems = [] } = useNews(cleaned);

  const chartEnd = new Date().toISOString().slice(0, 10);
  const { points, latest } = usePrices(cleaned, "2008-01-01", chartEnd);
  const display = resolveDisplayPrice(company, latest);
  const currentPrice = display.price;

  return (
    <div className="flex flex-col">
      {/* Price-move banner above the workstation — full-width MSN-style
          "▲ Price up +X% from previous close" bar so a reader knows the
          direction/magnitude before parsing the chart. Component is
          null-safe: renders nothing when either changePct or currentPrice
          is missing. */}
      {display.price != null && display.changePct != null && (
        <div className="w-full px-4 pt-4 sm:px-6 lg:px-8">
          <PriceMoveBanner
            currentPrice={display.price}
            previousClose={display.previousClose}
            changePct={display.changePct}
            priceDate={display.asOf}
          />
        </div>
      )}

      <TradingWorkstation key={cleaned} short={cleaned} />

      {/* Analysis stack, edge-to-edge (matches the workstation's rule).
          Order: returns calculator (interactive) → valuation table →
          fundamental radar → financials → AI narrative → deep analysis
          → news → filings. Sections that need a data feed we don't have
          for this ticker render as their own empty state — none of them
          block the workstation. */}
      <div className="w-full space-y-4 py-6">
        {points.length > 0 && (
          <ReturnsCalculator
            ticker={cleaned}
            history={points}
            financials={financials}
            currentPrice={currentPrice}
          />
        )}
        {company && (
          <ValuationPanel
            company={company}
            financials={financials ?? null}
            fundamentals={fundamentals ?? null}
          />
        )}
        {company && (
          <RadarScoreCard
            company={company}
            financials={financials}
            currentPrice={currentPrice}
          />
        )}
        <FinancialsPanel ticker={cleaned} />
        <FinancialNarrativeCard ticker={cleaned} />
        <DeepAnalysisPanel ticker={cleaned} />
        {(technicals || snapshot) && (
          <AIInsightsPanel
            technicals={technicals}
            snapshot={snapshot}
            currentPrice={currentPrice}
          />
        )}
        {financials && <NewsPanel financials={financials} newsItems={newsItems} />}
        {financials && <FilingsPanel financials={financials} />}
      </div>
    </div>
  );
};
