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

function getRows(type: Props["type"], market: MarketOverviewDoc, companies: CompanyDoc[]): CompanyDoc[] {
  const companyMap = new Map(companies.map(c => [c.ticker, c]));
  if (type === "gainers") {
    return market.top_gainers.slice(0, 5).map(g => companyMap.get(g.ticker)).filter((c): c is CompanyDoc => c != null);
  }
  if (type === "losers") {
    return market.top_losers.slice(0, 5).map(l => companyMap.get(l.ticker)).filter((c): c is CompanyDoc => c != null);
  }
  return [...companies].filter(c => c.change_pct_today != null).sort((a, b) => Math.abs(b.change_pct_today!) - Math.abs(a.change_pct_today!)).slice(0, 5);
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
                <Link to={`/company/${company.ticker}`} className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-raised/60">
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
