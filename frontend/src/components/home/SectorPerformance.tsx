import type { FC } from "react";
import type { MarketOverviewDoc } from "../../types";

type Props = { market: MarketOverviewDoc };

export const SectorPerformance: FC<Props> = ({ market }) => {
  const sectors = Object.entries(market.sector_performance);
  if (sectors.length === 0) return null;

  const sorted = [...sectors].sort(([, a], [, b]) => b - a);
  const maxAbs = Math.max(...sorted.map(([, v]) => Math.abs(v)), 0.01);

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam/60 px-4 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">Sector Performance</p>
      </div>
      <ul className="divide-y divide-seam/40">
        {sorted.map(([name, pct]) => {
          const up = pct >= 0;
          const barW = Math.round((Math.abs(pct) / maxAbs) * 100);
          return (
            <li key={name} className="flex items-center gap-3 px-4 py-2">
              <span className="w-36 shrink-0 truncate text-xs text-sub">{name}</span>
              <div className="relative flex-1 h-1.5 rounded-full bg-raised">
                <div
                  className={`absolute inset-y-0 left-0 rounded-full ${up ? "bg-emerald-500" : "bg-red-500"}`}
                  style={{ width: `${barW}%` }}
                />
              </div>
              <span className={`w-14 text-right font-mono text-xs font-semibold ${up ? "text-emerald-500" : "text-red-500"}`}>
                {up ? "+" : ""}{pct.toFixed(1)}%
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
};
