import type { FC } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

export type CompareLine = {
  ticker: string;
  short: string;
  color: string;
  points: { date: string; price: number }[];
};

type Props = {
  series: CompareLine[];
  height?: number;
};

// Merge & normalize: for each series, base = first non-null price in the
// timeframe, then pct[i] = (price / base − 1) × 100. Series are aligned on
// the union of dates so gaps for illiquid tickers stay honest (Line's
// connectNulls carries the visual line across without inventing numbers).
function buildDataset(series: CompareLine[]) {
  const dateSet = new Set<string>();
  series.forEach((s) => s.points.forEach((p) => dateSet.add(p.date)));
  const dates = Array.from(dateSet).sort();

  const normalized = series.map((s) => {
    const base = s.points.length > 0 ? s.points[0].price : null;
    const m = new Map<string, number>();
    if (base != null && base > 0) {
      s.points.forEach((p) => m.set(p.date, ((p.price / base) - 1) * 100));
    }
    return { ticker: s.ticker, short: s.short, color: s.color, map: m };
  });

  return dates.map((d) => {
    const row: Record<string, string | number | null> = { date: d };
    normalized.forEach((s) => {
      row[s.ticker] = s.map.has(d) ? s.map.get(d)! : null;
    });
    return row;
  });
}

const CompareTooltip: FC<{
  active?: boolean;
  payload?: { value: number | null; color: string; dataKey: string }[];
  label?: string;
  seriesMeta: Map<string, { short: string }>;
}> = ({ active, payload, label, seriesMeta }) => {
  if (!active || !payload?.length) return null;
  const sorted = [...payload].sort((a, b) => (b.value ?? -Infinity) - (a.value ?? -Infinity));
  return (
    <div className="rounded-md border border-rim bg-surface/95 px-3 py-2 shadow-xl backdrop-blur">
      <p className="mb-1 font-mono text-[10px] tabular-nums text-hint">{label}</p>
      <div className="space-y-0.5">
        {sorted.map((p) => {
          const meta = seriesMeta.get(p.dataKey);
          const v = p.value;
          return (
            <div key={p.dataKey} className="flex items-center gap-3">
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2 w-2 rounded-sm"
                  style={{ backgroundColor: p.color }}
                  aria-hidden="true"
                />
                <span className="text-[11px] font-semibold text-ink">
                  {meta?.short ?? p.dataKey}
                </span>
              </span>
              <span
                className={`ml-auto font-mono text-[11px] tabular-nums ${
                  v == null
                    ? "text-hint"
                    : v >= 0
                    ? "text-emerald-500"
                    : "text-red-500"
                }`}
              >
                {v == null ? "—" : `${v >= 0 ? "+" : "−"}${Math.abs(v).toFixed(2)}%`}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const CompareChart: FC<Props> = ({ series, height = 620 }) => {
  if (!series.length) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-seam text-xs text-hint"
        style={{ height }}
      >
        No series selected.
      </div>
    );
  }

  const data = buildDataset(series);
  const seriesMeta = new Map(series.map((s) => [s.ticker, { short: s.short }]));

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 48, bottom: 8, left: 8 }}>
          <CartesianGrid stroke="rgb(var(--seam))" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "rgb(var(--hint))", fontSize: 10 }}
            minTickGap={60}
          />
          <YAxis
            orientation="right"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "rgb(var(--hint))", fontSize: 10 }}
            width={52}
            tickFormatter={(v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`}
          />
          <Tooltip
            content={<CompareTooltip seriesMeta={seriesMeta} />}
            cursor={{ stroke: "rgb(var(--hint))", strokeWidth: 1, strokeDasharray: "3 3" }}
          />
          {/* Zero baseline via a Recharts hack: fake series drawn as a
              horizontal reference wouldn't add value here — the grid + %
              tick format already makes "0%" legible. */}
          {series.map((s) => (
            <Line
              key={s.ticker}
              type="monotone"
              dataKey={s.ticker}
              name={s.short}
              stroke={s.color}
              strokeWidth={1.75}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};
