import type { FC } from "react";
import { useMemo } from "react";
import {
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
} from "recharts";
import type { PricePoint } from "../../types";

interface ComputedFib {
  pct: number;
  label: string;
  color: string;
  price: number;
}

interface Props {
  data: PricePoint[];
  color: string;
  showFib?: boolean;
  sma20?: number | null;
  sma50?: number | null;
  sma200?: number | null;
  height?: number;
}

const FIB_LEVELS = [
  { pct: 0,    label: "0%",    color: "#ef4444" },
  { pct: 23.6, label: "23.6%", color: "#f97316" },
  { pct: 38.2, label: "38.2%", color: "#eab308" },
  { pct: 50,   label: "50.0%", color: "#22c55e" },
  { pct: 61.8, label: "61.8%", color: "#38bdf8" },
  { pct: 78.6, label: "78.6%", color: "#a78bfa" },
  { pct: 100,  label: "100%",  color: "#ef4444" },
];

const priceFmt = (v: number) =>
  v >= 1000 ? `${(v / 1000).toFixed(2)}k` : v.toFixed(2);

// Colored pill label for each Fibonacci level — rendered right of the chart plot area
const FibLabel: FC<{
  viewBox?: { x: number; y: number; width: number };
  fib: ComputedFib;
}> = ({ viewBox, fib }) => {
  if (!viewBox) return null;
  const { x, y, width } = viewBox;
  const rx = x + width + 6;
  const W = 92;
  return (
    <g style={{ pointerEvents: "none" }}>
      <rect x={rx} y={y - 9} width={W} height={18} rx={3} fill={fib.color} fillOpacity={0.14} />
      <rect x={rx} y={y - 9} width={W} height={18} rx={3} fill="none" stroke={fib.color} strokeOpacity={0.4} strokeWidth={0.8} />
      <text x={rx + 6} y={y + 4.5} fontSize={9.5} fill={fib.color} fontWeight="700" fontFamily="ui-monospace,monospace">
        {fib.label}
      </text>
      <text x={rx + W - 6} y={y + 4.5} fontSize={9.5} fill={fib.color} fontWeight="600" textAnchor="end" fontFamily="ui-monospace,monospace">
        {priceFmt(fib.price)}
      </text>
    </g>
  );
};

// Solid price label for the current price — like TradingView's live price badge
const CurrentPriceLabel: FC<{
  viewBox?: { x: number; y: number; width: number };
  price: number;
  bgColor: string;
}> = ({ viewBox, price, bgColor }) => {
  if (!viewBox) return null;
  const { x, y, width } = viewBox;
  const rx = x + width + 6;
  const W = 92;
  return (
    <g style={{ pointerEvents: "none" }}>
      <rect x={rx} y={y - 9} width={W} height={18} rx={3} fill={bgColor} fillOpacity={0.92} />
      <text x={rx + W / 2} y={y + 4.5} fontSize={10} fill="#fff" fontWeight="700" textAnchor="middle" fontFamily="ui-monospace,monospace">
        {priceFmt(price)}
      </text>
    </g>
  );
};

export const TradingChart: FC<Props> = ({
  data,
  color,
  showFib = true,
  sma20,
  sma50,
  sma200,
  height = 380,
}) => {
  const { lo, hi, fibs } = useMemo(() => {
    if (!data.length) return { lo: 0, hi: 1, fibs: [] as ComputedFib[] };
    const prices = data.map((p) => p.price);
    const lo = Math.min(...prices);
    const hi = Math.max(...prices);
    const range = hi - lo || 1;
    return {
      lo,
      hi,
      fibs: FIB_LEVELS.map((f) => ({ ...f, price: lo + (f.pct / 100) * range })),
    };
  }, [data]);

  const pad = (hi - lo) * 0.06;
  const lastPrice = data[data.length - 1]?.price ?? null;
  const step = Math.max(1, Math.floor(data.length / 8));
  const gradId = `tvg${color.replace(/[^a-z0-9]/gi, "")}`;

  const fmtTick = (d: string) => {
    const dt = new Date(d + "T00:00:00");
    return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  };

  return (
    // [&_svg]:overflow-visible lets fib labels and current-price label render in right margin
    <div className="[&_svg]:overflow-visible">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 16, right: 106, left: 2, bottom: 4 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={color} stopOpacity={0.28} />
              <stop offset="95%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>

          {/* Fibonacci zone shading — golden zone (38.2–61.8) intentionally brighter */}
          {showFib && fibs.length === 7 && (
            <>
              <ReferenceArea y1={fibs[5].price} y2={fibs[6].price} fill="#a78bfa" fillOpacity={0.055} ifOverflow="hidden" />
              <ReferenceArea y1={fibs[4].price} y2={fibs[5].price} fill="#38bdf8" fillOpacity={0.045} ifOverflow="hidden" />
              <ReferenceArea y1={fibs[2].price} y2={fibs[4].price} fill="#22c55e" fillOpacity={0.07}  ifOverflow="hidden" />
              <ReferenceArea y1={fibs[1].price} y2={fibs[2].price} fill="#eab308" fillOpacity={0.045} ifOverflow="hidden" />
              <ReferenceArea y1={fibs[0].price} y2={fibs[1].price} fill="#f97316" fillOpacity={0.045} ifOverflow="hidden" />
            </>
          )}

          <CartesianGrid strokeDasharray="3 4" stroke="#1c2030" vertical={false} />

          <XAxis
            dataKey="date"
            tick={{ fill: "#475569", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "#1e293b" }}
            interval={step - 1}
            tickFormatter={fmtTick}
          />
          <YAxis
            tick={{ fill: "#475569", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={56}
            domain={[lo - pad, hi + pad]}
            tickFormatter={priceFmt}
          />
          <Tooltip
            contentStyle={{
              background: "#0d1117",
              border: "1px solid #21262d",
              borderRadius: 6,
              fontSize: 12,
              boxShadow: "0 8px 32px rgba(0,0,0,0.7)",
            }}
            labelStyle={{ color: "#8b949e", marginBottom: 4, fontSize: 11 }}
            formatter={(v) => [`KES ${(v as number).toFixed(2)}`, "Close"]}
            labelFormatter={(lbl) => {
              const dt = new Date(String(lbl) + "T00:00:00");
              return dt.toLocaleDateString("en-GB", {
                weekday: "short", year: "numeric", month: "short", day: "numeric",
              });
            }}
            cursor={{ stroke: "#334155", strokeDasharray: "4 2", strokeWidth: 1 }}
          />

          {/* Fib level lines with right-side colored badge labels */}
          {showFib &&
            fibs.map((fib) => (
              <ReferenceLine
                key={fib.pct}
                y={fib.price}
                stroke={fib.color}
                strokeOpacity={0.55}
                strokeWidth={1}
                strokeDasharray={fib.pct === 0 || fib.pct === 100 ? undefined : "5 3"}
                label={(props: any) => <FibLabel {...props} fib={fib} />}
              />
            ))}

          {/* Moving average reference lines */}
          {sma20 != null && (
            <ReferenceLine y={sma20} stroke="#f59e0b" strokeWidth={1.2} strokeDasharray="4 2" strokeOpacity={0.7}
              label={{ value: "SMA20", position: "insideTopLeft", fill: "#f59e0b", fontSize: 9, fontWeight: 600 }} />
          )}
          {sma50 != null && (
            <ReferenceLine y={sma50} stroke="#38bdf8" strokeWidth={1.2} strokeDasharray="4 2" strokeOpacity={0.7}
              label={{ value: "SMA50", position: "insideTopLeft", fill: "#38bdf8", fontSize: 9, fontWeight: 600 }} />
          )}
          {sma200 != null && (
            <ReferenceLine y={sma200} stroke="#a78bfa" strokeWidth={1.2} strokeDasharray="4 2" strokeOpacity={0.7}
              label={{ value: "SMA200", position: "insideTopLeft", fill: "#a78bfa", fontSize: 9, fontWeight: 600 }} />
          )}

          {/* Current price dashed line + solid badge */}
          {lastPrice != null && (
            <ReferenceLine
              y={lastPrice}
              stroke={color}
              strokeDasharray="4 2"
              strokeWidth={1}
              strokeOpacity={0.9}
              label={(props: any) => <CurrentPriceLabel {...props} price={lastPrice} bgColor={color} />}
            />
          )}

          <Area
            type="monotone"
            dataKey="price"
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradId})`}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0, fill: color }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
