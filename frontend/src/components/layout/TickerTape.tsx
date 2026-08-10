import { useState } from "react";
import type { FC } from "react";
import { Link } from "react-router-dom";
import { useMarketOverview } from "../../hooks/useMarket";
import { useCompanies } from "../../hooks/useCompanies";
import type { CompanyDoc } from "../../types";

// Inline logo for the tape — CompanyLogo "sm" size (h-8 w-8) is too large
const SmallLogo: FC<Pick<CompanyDoc, "id" | "short" | "color" | "icon">> = ({ id, short, color, icon }) => {
  const [failed, setFailed] = useState(false);
  if (!failed) {
    return (
      <img
        src={`/logos/${id}.png`}
        alt={short}
        className="h-4 w-4 rounded object-contain"
        onError={() => setFailed(true)}
      />
    );
  }
  return (
    <span
      role="img"
      aria-label={short}
      className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-[9px]"
      style={{ backgroundColor: `${color}22`, border: `1px solid ${color}55` }}
    >
      {icon}
    </span>
  );
};

const Chip: FC<{ pct: number }> = ({ pct }) => {
  const up = pct >= 0;
  return (
    <span className={`font-mono text-[11px] font-semibold ${up ? "text-emerald-500" : "text-red-500"}`}>
      {up ? "▲" : "▼"} {Math.abs(pct).toFixed(2)}%
    </span>
  );
};

export const TickerTape: FC = () => {
  const { data: market } = useMarketOverview();
  const { data: companies = [] } = useCompanies();

  if (!market) return null;

  const companyMap = new Map(companies.map(c => [c.ticker, c]));
  const gainers = market.top_gainers.slice(0, 5);
  const losers = market.top_losers.slice(0, 5);

  // Accepts a prefix so the duplicate copy has unique React keys
  const renderItems = (prefix: string) => (
    <>
      <span className="flex items-center gap-1.5">
        <span className="text-[11px] font-semibold text-muted">NSE 20</span>
        {market.nse20_value != null && (
          <span className="font-mono text-[11px] text-ink">{market.nse20_value.toFixed(2)}</span>
        )}
        {market.nse20_change_pct != null && <Chip pct={market.nse20_change_pct} />}
      </span>

      <span className="text-hint" aria-hidden="true">|</span>

      {gainers.map(g => {
        const c = companyMap.get(g.ticker);
        return (
          <Link
            key={`${prefix}-g-${g.ticker}`}
            to={`/chart/${g.ticker}`}
            className="flex items-center gap-1 transition-opacity hover:opacity-80"
          >
            {c && <SmallLogo id={c.id} short={c.short} color={c.color} icon={c.icon} />}
            <span className="text-[11px] font-semibold text-ink">{g.ticker}</span>
            <Chip pct={g.change_pct} />
          </Link>
        );
      })}

      <span className="text-hint" aria-hidden="true">|</span>

      {losers.map(l => {
        const c = companyMap.get(l.ticker);
        return (
          <Link
            key={`${prefix}-l-${l.ticker}`}
            to={`/chart/${l.ticker}`}
            className="flex items-center gap-1 transition-opacity hover:opacity-80"
          >
            {c && <SmallLogo id={c.id} short={c.short} color={c.color} icon={c.icon} />}
            <span className="text-[11px] font-semibold text-ink">{l.ticker}</span>
            <Chip pct={l.change_pct} />
          </Link>
        );
      })}
    </>
  );

  return (
    <>
      <style>{`
        @keyframes marquee {
          from { transform: translateX(0); }
          to   { transform: translateX(-50%); }
        }
        .ticker-track { animation: marquee 40s linear infinite; }
        .ticker-tape:hover .ticker-track { animation-play-state: paused; }
      `}</style>
      <div className="ticker-tape sticky top-14 z-40 hidden h-8 overflow-hidden border-b border-seam bg-surface sm:block">
        <div className="ticker-track flex h-full w-max items-center gap-4 px-4">
          {renderItems("a")}
          {renderItems("b")}
        </div>
      </div>
    </>
  );
};
