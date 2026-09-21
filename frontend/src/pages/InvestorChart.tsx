import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import { useFinancials as useFinancialsDoc } from "../hooks/useCompany";
import { FilingsPanel } from "../components/investor/FilingsPanel";
import { TradingWorkstation } from "../components/investor/TradingWorkstation";
import { cleanTicker } from "../lib/timeframe";

// 2026-09-21 rewrite:
// Every ticker click across the app (Home tiles, movers table, top signals,
// watchlist rail, ticker tape, peer chips, Companies list, Screener rows,
// recent tickers strip) routes to this page. Previously we rendered a small
// area chart inside a max-w-[1600px] two-column shell with the LeftWatchlistRail
// on the left — that meant users clicked a ticker expecting a TradingView-
// level chart and got a cramped ~450px area chart instead.
//
// Now: this page IS the workstation. The TradingWorkstation component owns
// the top ribbon (with its own symbol search + watchlist), the left drawing
// rail, the main canvas, and the right sidebar. We render it at full viewport
// width and drop the redundant LeftWatchlistRail + ticker header (workstation
// already surfaces the ticker in its own sub-header).
//
// FilingsPanel stays underneath as secondary content — corporate actions
// aren't chart data and users still want them one scroll away.
export const InvestorChart = () => {
  const { ticker: rawTicker = "" } = useParams<{ ticker: string }>();
  const ticker = rawTicker.toUpperCase();
  const cleaned = cleanTicker(ticker);
  const pushRecent = useRecentTickers((s) => s.push);

  useEffect(() => {
    if (ticker) pushRecent(ticker);
  }, [ticker, pushRecent]);

  const { data: financials } = useFinancialsDoc(cleaned);

  return (
    <div className="flex flex-col gap-4">
      {/* Workstation is width-hungry — break out of the AppShell's max-w-7xl
          container so the chart + right sidebar have room to breathe. The
          negative margins undo the AppShell's px-4/sm:px-6/lg:px-8 padding
          and the -mt-6 removes the outer py-6 above the chart. Below the
          workstation we return to the shell's normal content width via a
          plain max-w-7xl mx-auto wrapper. */}
      <div className="-mx-4 -mt-6 sm:-mx-6 lg:-mx-8"
           style={{ width: "auto" }}>
        <TradingWorkstation short={cleaned} />
      </div>

      {financials && (
        <div className="mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8">
          <FilingsPanel financials={financials} />
        </div>
      )}
    </div>
  );
};
