import type { FC } from "react";
import { Link } from "react-router-dom";
import type { CompanyDoc, MarketOverviewDoc } from "../../types";

type Props = {
  type: "gainers" | "losers" | "active";
  market: MarketOverviewDoc;
  companies: CompanyDoc[];
};

const HEADERS: Record<Props["type"], string> = {
  gainers: "Top Gainers",
  losers:  "Top Losers",
  active:  "Most Active",
};

// Compute movers from LIVE change_pct_today on each company doc rather
// than the pre-computed market_overview.top_gainers/losers arrays. Those
// are a snapshot from some earlier point in the day, so tickers on the
// snapshot's gainers list may have flipped negative by the time the user
// loads the page — the box would then show a "Top Gainer" with a red
// negative %.
//
// Sorting from the live doc guarantees the box's %-values match its
// label. Ties/nulls filtered out.
function getRows(_type: Props["type"], _market: MarketOverviewDoc, companies: CompanyDoc[]): CompanyDoc[] {
  const withPct = companies.filter(c => c.change_pct_today != null);
  const type = _type;
  if (type === "gainers") {
    return withPct
      .filter(c => (c.change_pct_today ?? 0) > 0)
      .sort((a, b) => (b.change_pct_today ?? 0) - (a.change_pct_today ?? 0))
      .slice(0, 5);
  }
  if (type === "losers") {
    return withPct
      .filter(c => (c.change_pct_today ?? 0) < 0)
      .sort((a, b) => (a.change_pct_today ?? 0) - (b.change_pct_today ?? 0))
      .slice(0, 5);
  }
  return withPct
    .sort((a, b) => Math.abs(b.change_pct_today!) - Math.abs(a.change_pct_today!))
    .slice(0, 5);
}

export const MoversTable: FC<Props> = ({ type, market, companies }) => {
  const rows = getRows(type, market, companies);

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="flex items-center justify-between border-b border-seam/60 px-4 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted">{HEADERS[type]}</span>
        <span className="text-[10px] text-hint">{rows.length} of {companies.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm text-muted">No data available</p>
      ) : (
        <ul>
          {rows.map(company => {
            const pct = company.change_pct_today;
            return (
              <li key={company.ticker}>
                <Link to={`/chart/${company.ticker}`} className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-raised/60">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-ink">{company.short}</p>
                    <p className="font-mono text-[10px] text-muted">{company.ticker}</p>
                  </div>
                  <div className="text-right">
                    {company.current_price != null && (
                      <p className="font-mono text-xs text-sub">KES {company.current_price.toFixed(2)}</p>
                    )}
                    {pct != null && (
                      <p className={`font-mono text-xs font-semibold ${pct >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                        {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                      </p>
                    )}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
