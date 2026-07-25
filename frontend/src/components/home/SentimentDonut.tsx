import type { FC } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import type { MarketOverviewDoc } from "../../types";

type Props = { market: MarketOverviewDoc };

const SEGMENTS = [
  { key: "BUY"  as const, color: "#10b981" },
  { key: "HOLD" as const, color: "#f59e0b" },
  { key: "SELL" as const, color: "#ef4444" },
];

export const SentimentDonut: FC<Props> = ({ market }) => {
  const dist = market.signal_distribution;
  const total = dist.BUY + dist.HOLD + dist.SELL;
  const data = SEGMENTS.map(s => ({ name: s.key, value: dist[s.key], color: s.color })).filter(d => d.value > 0);
  const dominant = data.length > 0 ? data.reduce((a, b) => a.value > b.value ? a : b) : null;

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam/60 px-4 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">Market Sentiment</p>
      </div>
      <div className="flex items-center gap-4 px-4 py-3">
        <div className="relative h-24 w-24 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} innerRadius="40%" outerRadius="65%" dataKey="value" startAngle={90} endAngle={-270} paddingAngle={2} isAnimationActive={false}>
                {data.map(entry => <Cell key={entry.name} fill={entry.color} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          {dominant && (
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[10px] font-bold leading-none" style={{ color: dominant.color }}>{dominant.name}</span>
              <span className="text-[9px] text-hint">top</span>
            </div>
          )}
        </div>
        <div className="space-y-1.5">
          {SEGMENTS.map(s => {
            const count = dist[s.key];
            return (
              <div key={s.key} className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
                <span className="w-8 text-xs text-sub">{s.key}</span>
                <span className="font-mono text-xs font-semibold text-ink">{count}</span>
                {total > 0 && <span className="text-[10px] text-hint">{((count / total) * 100).toFixed(0)}%</span>}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
