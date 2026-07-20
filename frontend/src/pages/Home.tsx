import type { FC } from "react";
import { Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { useMarketOverview } from "../hooks/useMarket";

export const Home: FC = () => {
  const { data: market, isLoading, isError } = useMarketOverview();

  return (
    <PageShell>
      <div className="space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-ink">NSE Market Overview</h1>
          <p className="mt-1 text-sub">
            Nairobi Securities Exchange — AI-powered analytics
          </p>
        </div>

        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <Spinner size="lg" />
          </div>
        )}

        {isError && (
          <Card className="border-red-800 bg-red-950/20">
            <p className="text-red-400">Failed to load market data. Please try again.</p>
          </Card>
        )}

        {market && (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            <Card>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">
                Signal Distribution
              </h2>
              <div className="flex gap-6">
                <div className="text-center">
                  <p className="text-2xl font-bold text-emerald-400">
                    {market.signal_distribution.BUY}
                  </p>
                  <SignalBadge signal="BUY" />
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-amber-400">
                    {market.signal_distribution.HOLD}
                  </p>
                  <SignalBadge signal="HOLD" />
                </div>
                <div className="text-center">
                  <p className="text-2xl font-bold text-red-400">
                    {market.signal_distribution.SELL}
                  </p>
                  <SignalBadge signal="SELL" />
                </div>
              </div>
            </Card>

            <Card>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">
                Top Gainers
              </h2>
              <ul className="space-y-2">
                {market.top_gainers.slice(0, 3).map((g) => (
                  <li key={g.ticker} className="flex items-center justify-between">
                    <Link
                      to={`/company/${g.ticker}`}
                      className="text-sm font-medium text-sub hover:text-accent"
                    >
                      {g.ticker}
                    </Link>
                    <span className="text-sm font-medium text-emerald-500">
                      +{g.change_pct.toFixed(2)}%
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card>
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted">
                Top Losers
              </h2>
              <ul className="space-y-2">
                {market.top_losers.slice(0, 3).map((l) => (
                  <li key={l.ticker} className="flex items-center justify-between">
                    <Link
                      to={`/company/${l.ticker}`}
                      className="text-sm font-medium text-sub hover:text-accent"
                    >
                      {l.ticker}
                    </Link>
                    <span className="text-sm font-medium text-red-500">
                      {l.change_pct.toFixed(2)}%
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        )}

        {!isLoading && !isError && !market && (
          <Card>
            <p className="text-sub">
              No market data yet. Pipeline runs daily at 18:00 EAT.
            </p>
          </Card>
        )}

        <p className="text-center text-sm">
          <Link to="/companies" className="text-accent hover:underline">
            View all companies →
          </Link>
        </p>
      </div>
    </PageShell>
  );
};
