import type { FC } from "react";
import {
  ComposedChart,
  Area,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { RtdbPricePoint } from "../../hooks/useHistoricalPrices";

type FocusedPricePoint = {
  date: string;
  price: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  up: boolean;
};

const priceFmt = new Intl.NumberFormat("en-KE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const volumeFmt = (v: number | null): string => {
  if (v == null) return "—";
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString();
};

const CustomTooltip: FC<{
  active?: boolean;
  payload?: { payload: FocusedPricePoint }[];
}> = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-md border border-rim bg-surface/95 px-3 py-2 text-[11px] shadow-xl backdrop-blur">
      <div className="grid grid-cols-[auto_auto] gap-x-4 gap-y-0.5 font-mono">
        <span className="text-muted">Open</span>
        <span className="text-right text-ink">{p.open != null ? priceFmt.format(p.open) : "—"}</span>
        <span className="text-muted">High</span>
        <span className="text-right text-ink">{p.high != null ? priceFmt.format(p.high) : "—"}</span>
        <span className="text-muted">Low</span>
        <span className="text-right text-ink">{p.low != null ? priceFmt.format(p.low) : "—"}</span>
        <span className="text-muted">Close</span>
        <span className="text-right text-ink">{priceFmt.format(p.price)}</span>
        <span className="text-muted">Volume</span>
        <span className="text-right text-ink">{volumeFmt(p.volume)}</span>
      </div>
      <p className="mt-1.5 border-t border-seam pt-1 text-center text-[10px] text-hint">{p.date}</p>
    </div>
  );
};

type FocusedPriceChartProps = {
  data: RtdbPricePoint[];
  color?: string;
  height?: number;
};

export const FocusedPriceChart: FC<FocusedPriceChartProps> = ({
  data,
  color = "rgb(var(--accent))",
  height = 560,
}) => {
  if (data.length < 1) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-dashed border-seam text-xs text-hint"
        style={{ height }}
      >
        No price data available for this timeframe.
      </div>
    );
  }

  const points: FocusedPricePoint[] = data
    // Drop c=0 rows too — legacy RTDB fills that would render vertical
    // drop-to-axis spikes on the area chart.
    .filter((p) => p.c != null && (p.c as number) > 0)
    .map((p) => ({
      date: p.date,
      price: p.c as number,
      open: p.o,
      high: p.h,
      low: p.l,
      volume: p.v,
      up: (p.ch ?? 0) >= 0,
    }));

  if (points.length === 1) {
    points.push({ ...points[0] });
  }

  const chartHeight = height;
  const priceHeightRatio = 0.78;

  return (
    <div style={{ width: "100%", height: chartHeight }}>
      <ResponsiveContainer>
        <ComposedChart data={points} margin={{ top: 8, right: 48, bottom: 8, left: 8 }}>
          <defs>
            <linearGradient id="focusedGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset={`${priceHeightRatio * 100}%`} stopColor={color} stopOpacity={0.02} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke="rgb(var(--seam))" strokeDasharray="2 4" vertical={false} />

          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "rgb(var(--hint))", fontSize: 10 }}
            minTickGap={60}
          />

          <YAxis
            yAxisId="price"
            orientation="right"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "rgb(var(--hint))", fontSize: 10 }}
            width={44}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(2)}K` : v.toFixed(2))}
          />

          <YAxis
            yAxisId="volume"
            orientation="left"
            hide
            domain={[0, (dataMax: number) => dataMax * 4]}
          />

          <Tooltip
            content={<CustomTooltip />}
            cursor={{ stroke: color, strokeWidth: 1, strokeDasharray: "3 3" }}
          />

          <Area
            yAxisId="price"
            type="monotone"
            dataKey="price"
            stroke={color}
            strokeWidth={1.75}
            fill="url(#focusedGrad)"
            isAnimationActive={false}
            dot={false}
          />

          <Bar yAxisId="volume" dataKey="volume" isAnimationActive={false} barSize={2}>
            {points.map((p, i) => (
              <Cell
                key={i}
                fill={p.up ? "rgb(34 197 94 / 0.45)" : "rgb(239 68 68 / 0.45)"}
              />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
