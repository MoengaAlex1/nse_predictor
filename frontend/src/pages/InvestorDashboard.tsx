import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";

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
  const pushRecent = useRecentTickers((s) => s.push);

  useEffect(() => {
    if (ticker) pushRecent(ticker);
  }, [ticker, pushRecent]);

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8">
      <div className="mb-3 flex items-baseline gap-2">
        <h1 className="text-lg font-semibold text-ink">{ticker || "—"}</h1>
        <span className="text-xs text-hint">Investor dashboard — Phase A shell</span>
      </div>

      <div className="grid gap-3 lg:grid-cols-[240px_minmax(0,1fr)_320px]">
        <PlaceholderBlock label="Left rail — Watchlist + Suggested (Phase C)" height="h-[560px]" />

        <div className="flex flex-col gap-3">
          <PlaceholderBlock label="Price header + timeframe tabs (Phase B)" height="h-24" />
          <PlaceholderBlock label="Area chart (Phase B)" height="h-72" />
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

        <PlaceholderBlock label="Right rail — Day Range + Key Stats (Phase B)" height="h-[560px]" />
      </div>
    </div>
  );
};
