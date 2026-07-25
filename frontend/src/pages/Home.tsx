import type { FC } from "react";
import { Link } from "react-router-dom";
import { Spinner } from "../components/ui/Spinner";
import { Card } from "../components/ui/Card";
import { useMarketOverview } from "../hooks/useMarket";
import { useCompanies } from "../hooks/useCompanies";
import { MarketSummaryStrip } from "../components/home/MarketSummaryStrip";
import { MoversTable } from "../components/home/MoversTable";
import { SentimentDonut } from "../components/home/SentimentDonut";
import { SectorPerformance } from "../components/home/SectorPerformance";
import { TopSignals } from "../components/home/TopSignals";

export const Home: FC = () => {
  const { data: market, isLoading: marketLoading, isError: marketError } = useMarketOverview();
  const { data: companies = [] } = useCompanies();

  const isLoading = marketLoading;
  const isError = marketError;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-ink">NSE Market Intelligence</h1>
        <p className="mt-1 text-sub">Nairobi Securities Exchange — AI-powered analytics</p>
      </div>

      {isLoading && (
        <div className="flex justify-center py-16">
          <Spinner size="lg" />
        </div>
      )}

      {isError && (
        <Card className="border-red-800 bg-red-950/20">
          <p className="text-red-400">Failed to load market data. Please try again.</p>
        </Card>
      )}

      {!isLoading && !isError && !market && (
        <Card>
          <p className="text-sub">No market data yet. Pipeline runs daily at 18:00 EAT.</p>
        </Card>
      )}

      {market && (
        <>
          <MarketSummaryStrip market={market} companies={companies} />

          <div className="grid gap-6 lg:grid-cols-3">
            {/* Main column — movers */}
            <div className="space-y-4 lg:col-span-2">
              <div className="grid gap-4 sm:grid-cols-3">
                <MoversTable type="gainers" market={market} companies={companies} />
                <MoversTable type="losers" market={market} companies={companies} />
                <MoversTable type="active" market={market} companies={companies} />
              </div>
              <SectorPerformance market={market} />
            </div>

            {/* Sidebar — sentiment + signals */}
            <div className="space-y-4">
              <SentimentDonut market={market} />
              <TopSignals companies={companies} />
            </div>
          </div>

          <p className="text-center text-sm">
            <Link to="/companies" className="text-accent hover:underline">
              View all companies →
            </Link>
          </p>
        </>
      )}
    </div>
  );
};
