import type { FC } from "react";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import type { PricePoint } from "../../types";

type PriceAreaChartProps = {
  data: PricePoint[];
  color?: string;
  height?: number;
};

const nf = new Intl.NumberFormat("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const CustomTooltip: FC<{
  active?: boolean;
  payload?: { value: number; payload: PricePoint }[];
}> = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-md border border-rim bg-surface px-2.5 py-1.5 text-xs shadow-lg">
      <p className="font-mono text-[10px] text-muted">{p.date}</p>
      <p className="mt-0.5 font-mono font-semibold text-ink">KES {nf.format(p.price)}</p>
    </div>
  );
};

export const PriceAreaChart: FC<PriceAreaChartProps> = ({
  data,
  color = "rgb(var(--accent))",
  height = 280,
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

  const singlePoint = data.length === 1;
  const chartData = singlePoint ? [data[0], data[0]] : data;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <AreaChart data={chartData} margin={{ top: 10, right: 8, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id="priceAreaGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgb(var(--seam))" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fill: "rgb(var(--hint))", fontSize: 10 }}
            minTickGap={40}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "rgb(var(--hint))", fontSize: 10 }}
            width={44}
            orientation="right"
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => v.toFixed(2)}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: color, strokeWidth: 1, strokeDasharray: "3 3" }} />
          <Area
            type="monotone"
            dataKey="price"
            stroke={color}
            strokeWidth={1.75}
            fill="url(#priceAreaGradient)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
