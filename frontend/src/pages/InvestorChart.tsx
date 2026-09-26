import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import { useCompany, useFinancials as useFinancialsDoc } from "../hooks/useCompany";
import { usePrices } from "../hooks/usePrices";
import { FilingsPanel } from "../components/investor/FilingsPanel";
import { ReturnsCalculator } from "../components/investor/ReturnsCalculator";
import { TradingWorkstation } from "../components/investor/TradingWorkstation";
import { toBase } from "../lib/ticker";

// InvestorChart is the workstation page: TradingWorkstation up top, then a
// full-width analysis stack (Returns Calculator + Filings Library) below.
// All three sections share the same horizontal container so they line up
// at the same left/right edges — the previous layout let the workstation
// go edge-to-edge while boxing FilingsPanel inside max-w-7xl, which made
// the sections look mis-aligned on wide screens.
export const InvestorChart = () => {
  const { ticker: rawTicker = "" } = useParams<{ ticker: string }>();
  const cleaned = toBase(rawTicker);
  const pushRecent = useRecentTickers((s) => s.push);

  useEffect(() => {
    if (cleaned) pushRecent(cleaned);
  }, [cleaned, pushRecent]);

  const { data: financials } = useFinancialsDoc(cleaned);
  const { data: company } = useCompany(cleaned);

  const chartEnd = new Date().toISOString().slice(0, 10);
  const { points, latest } = usePrices(cleaned, "2008-01-01", chartEnd);
  const currentPrice = latest?.c ?? company?.current_price ?? null;

  return (
    <div className="flex flex-col">
      <TradingWorkstation key={cleaned} short={cleaned} />

      {/* No horizontal padding here on purpose: the TradingWorkstation above
          is edge-to-edge (border-y, w-full, no max-width) and the user's
          alignment complaint was that FilingsPanel was inset relative to
          the chart. Both sections now share the viewport edges so the
          eye follows a single left/right rule down the page. */}
      <div className="w-full space-y-4 px-4 py-6 sm:px-6 lg:px-8">
        {points.length > 0 && (
          <ReturnsCalculator
            ticker={cleaned}
            history={points}
            financials={financials}
            currentPrice={currentPrice}
          />
        )}
        {financials && <FilingsPanel financials={financials} />}
      </div>
    </div>
  );
};
