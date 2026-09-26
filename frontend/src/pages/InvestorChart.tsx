import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import { useCompany } from "../hooks/useCompany";
import { usePrices } from "../hooks/usePrices";
import { resolveDisplayPrice } from "../lib/format";
import { TradingWorkstation } from "../components/investor/TradingWorkstation";
import { PriceMoveBanner } from "../components/investor/PriceMoveBanner";
import { CompanyDeepDive } from "./CompanyDeepDive";
import { toBase } from "../lib/ticker";

// Single canonical company page. The old /company/{ticker} route now
// redirects here. Layout order:
//   1. Price-move banner (MSN-style ▲/▼ pill above the fold)
//   2. TradingView-style workstation (chart, indicators, right sidebar)
//   3. Full analysis stack — Returns Calculator, Valuation, Financials,
//      Fundamental Radar, AI Signal, Forecast (1M/3M/6M/9M/12M),
//      Model Accuracy, Signal Backtest, News & Filings, etc. — all
//      rendered by <CompanyDeepDive embedded /> so nothing that used
//      to live on /company/{ticker} is missing.
export const InvestorChart = () => {
  const { ticker: rawTicker = "" } = useParams<{ ticker: string }>();
  const cleaned = toBase(rawTicker);
  const pushRecent = useRecentTickers((s) => s.push);

  useEffect(() => {
    if (cleaned) pushRecent(cleaned);
  }, [cleaned, pushRecent]);

  // Load just enough here to render the price-move banner above the
  // workstation. CompanyDeepDive below re-reads its own hooks (company,
  // snapshot, technicals, financials, fundamentals, news, macro) — the
  // duplicate reads are cheap because react-query dedupes on the same
  // query key.
  const { data: company } = useCompany(cleaned);
  const chartEnd = new Date().toISOString().slice(0, 10);
  const { latest } = usePrices(cleaned, "2008-01-01", chartEnd);
  const display = resolveDisplayPrice(company, latest);

  return (
    <div className="flex flex-col">
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

      {/* Full analysis stack. `embedded` suppresses CompanyDeepDive's
          own copy of the workstation + price banner so nothing renders
          twice, but every other section (ForecastPanel with 1M/3M/6M/
          9M/12M horizons, SnapshotCard AI signal, ValuationPanel,
          FinancialsPanel, RadarScoreCard, ModelAccuracyCard,
          SignalBacktestChart, ReturnsCalculator, PriceExplainer, the
          combined News & Filings tab, ChartSection technical chart,
          sidebar sliders) still ships. */}
      <div className="w-full px-4 py-6 sm:px-6 lg:px-8">
        <CompanyDeepDive tickerOverride={cleaned} embedded />
      </div>
    </div>
  );
};
