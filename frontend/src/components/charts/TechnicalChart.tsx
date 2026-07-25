import type { FC } from "react";
import { useMemo } from "react";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { RtdbPricePoint } from "../../hooks/useHistoricalPrices";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Props {
  data: RtdbPricePoint[];
  height?: number;
  chartType?: "candles" | "ohlc";
}

interface ChartRow {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  range: [number, number];
  sma20: number | null;
  sma50: number | null;
  sma100: number | null;
  sma200: number | null;
}

// ── SMA computation ────────────────────────────────────────────────────────────

function computeSMA(closes: number[], period: number): (number | null)[] {
  return closes.map((_, i) => {
    if (i < period - 1) return null;
    const sum = closes.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
    return sum / period;
  });
}

// ── Legend item ───────────────────────────────────────────────────────────────

const LegendItem: FC<{ color: string; label: string; dashed?: boolean; square?: boolean }> = ({
  color,
  label,
  dashed,
  square,
}) => (
  <span className="flex items-center gap-1 text-[10px] font-semibold text-muted">
    {square ? (
      <span style={{ backgroundColor: color }} className="inline-block h-2 w-2 rounded-sm" />
    ) : (
      <svg width={16} height={8}>
        <line
          x1={0}
          y1={4}
          x2={16}
          y2={4}
          stroke={color}
          strokeWidth={2}
          strokeDasharray={dashed ? "4 2" : undefined}
        />
      </svg>
    )}
    {label}
  </span>
);

// ── OHLC bar shape ────────────────────────────────────────────────────────────

const OhlcShape = (props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: ChartRow;
}) => {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props;
  if (!payload) return null;
  const { open, close, high, low } = payload;
  const isGreen = close >= open;
  const color = isGreen ? "#16a34a" : "#dc2626";
  const cx = x + width / 2;
  const priceRange = high - low;
  if (priceRange === 0) return null;
  const ppu = height / priceRange;
  const yHigh = y;
  const yLow = y + height;
  const yOpen = y + (high - open) * ppu;
  const yClose = y + (high - close) * ppu;
  const tickLen = Math.max(Math.min(width * 0.4, 6), 2);
  return (
    <g>
      {/* Vertical stem */}
      <line x1={cx} y1={yHigh} x2={cx} y2={yLow} stroke={color} strokeWidth={1.5} />
      {/* Open tick — left */}
      <line x1={cx - tickLen} y1={yOpen} x2={cx} y2={yOpen} stroke={color} strokeWidth={1.5} />
      {/* Close tick — right */}
      <line x1={cx} y1={yClose} x2={cx + tickLen} y2={yClose} stroke={color} strokeWidth={1.5} />
    </g>
  );
};

// ── Candlestick shape ─────────────────────────────────────────────────────────

const CandleShape = (props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: ChartRow;
}) => {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props;
  if (!payload) return null;
  const { open, close, high, low } = payload;
  const isGreen = close >= open;
  const color = isGreen ? "#16a34a" : "#dc2626";
  const cx = x + width / 2;
  const priceRange = high - low;
  if (priceRange === 0) return null;
  const ppu = height / priceRange;
  const bodyTop = y + (high - Math.max(open, close)) * ppu;
  const bodyHeight = Math.max(Math.abs(close - open) * ppu, 1);
  const candleW = Math.max(Math.min(width * 0.7, 12), 2);
  return (
    <g>
      <line x1={cx} y1={y} x2={cx} y2={y + height} stroke={color} strokeWidth={1} />
      <rect
        x={cx - candleW / 2}
        y={bodyTop}
        width={candleW}
        height={bodyHeight}
        fill={color}
      />
    </g>
  );
};

// ── Volume bar shape ──────────────────────────────────────────────────────────

const VolumeBar = (props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  payload?: ChartRow;
}) => {
  const { x = 0, y = 0, width = 0, height = 0, payload } = props;
  if (!payload) return null;
  const color = payload.close >= payload.open ? "#16a34a" : "#dc2626";
  return (
    <rect
      x={x}
      y={y}
      width={Math.max(width - 1, 1)}
      height={height}
      fill={color}
      opacity={0.7}
    />
  );
};

// ── OHLC tooltip ──────────────────────────────────────────────────────────────

const OhlcTooltip = ({ active, payload }: { active?: boolean; payload?: Array<{ payload: ChartRow }> }) => {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  const hl = d.high - d.low;
  const hlPct = d.low > 0 ? ((hl / d.low) * 100).toFixed(2) : "0.00";
  const varPrev = d.close - d.open;
  return (
    <div className="rounded border border-rim bg-surface px-3 py-2 text-[11px] shadow-lg">
      <p className="mb-1.5 font-mono text-[10px] font-semibold text-muted">{d.date}</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <span className="text-muted">Open</span>
        <span className="text-right font-mono text-sub">{d.open.toFixed(2)}</span>
        <span className="text-muted">High</span>
        <span className="text-right font-mono text-sub">{d.high.toFixed(2)}</span>
        <span className="text-muted">Low</span>
        <span className="text-right font-mono text-sub">{d.low.toFixed(2)}</span>
        <span className="text-muted">Close</span>
        <span className="text-right font-mono text-sub">{d.close.toFixed(2)}</span>
        <span className="text-muted">High-Low</span>
        <span className="text-right font-mono text-sub">{hlPct}%</span>
        <span className="text-sky-400">Var. / prev</span>
        <span
          className={`text-right font-mono font-semibold ${varPrev >= 0 ? "text-green-400" : "text-red-400"}`}
        >
          {varPrev >= 0 ? "+" : ""}
          {varPrev.toFixed(2)}
        </span>
      </div>
    </div>
  );
};

// ── Main component ─────────────────────────────────────────────────────────────

const TICK_COLOR = "#475569";
const GRID_COLOR = "rgba(255,255,255,0.06)";

export const TechnicalChart: FC<Props> = ({ data, height = 480, chartType = "candles" }) => {
  const chartData = useMemo<ChartRow[]>(() => {
    const valid = data.filter(
      (p) => p.o != null && p.h != null && p.l != null && p.c != null,
    );
    const closes = valid.map((p) => p.c as number);
    const sma20 = computeSMA(closes, 20);
    const sma50 = computeSMA(closes, 50);
    const sma100 = computeSMA(closes, 100);
    const sma200 = computeSMA(closes, 200);
    return valid.map((p, i) => ({
      date: p.date,
      open: p.o as number,
      high: p.h as number,
      low: p.l as number,
      close: p.c as number,
      volume: p.v ?? 0,
      range: [p.l as number, p.h as number] as [number, number],
      sma20: sma20[i],
      sma50: sma50[i],
      sma100: sma100[i],
      sma200: sma200[i],
    }));
  }, [data]);

  // Last non-null SMA values for ReferenceLine labels
  const lastSma20 = useMemo(
    () => [...chartData].reverse().find((d) => d.sma20 != null)?.sma20 ?? null,
    [chartData],
  );
  const lastSma50 = useMemo(
    () => [...chartData].reverse().find((d) => d.sma50 != null)?.sma50 ?? null,
    [chartData],
  );
  const lastSma100 = useMemo(
    () => [...chartData].reverse().find((d) => d.sma100 != null)?.sma100 ?? null,
    [chartData],
  );
  const lastSma200 = useMemo(
    () => [...chartData].reverse().find((d) => d.sma200 != null)?.sma200 ?? null,
    [chartData],
  );

  const step = Math.max(1, Math.floor(chartData.length / 8));

  const fmtTick = (d: string) => {
    const dt = new Date(d.includes("T") ? d : d + "T00:00:00");
    return isNaN(dt.getTime())
      ? d
      : dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  };

  const fmtPrice = (v: number) =>
    v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(2);

  const fmtVol = (v: number) =>
    v >= 1_000_000
      ? `${(v / 1_000_000).toFixed(1)}M`
      : v >= 1_000
      ? `${(v / 1_000).toFixed(0)}K`
      : String(v);

  if (!chartData.length) {
    return (
      <div
        style={{ height }}
        className="flex w-full items-center justify-center text-xs text-muted"
      >
        No OHLC data available for this range.
      </div>
    );
  }

  const mainHeight = Math.round((height ?? 480) * 0.78);
  const volHeight = (height ?? 480) - mainHeight;

  return (
    <div style={{ height }} className="w-full [&_svg]:overflow-visible">
      {/* Legend */}
      <div className="flex flex-wrap gap-3 px-2 py-1">
        <LegendItem color="#6b7280" label={chartType === "ohlc" ? "OHLC" : "Candles"} square />
        <LegendItem color="#3b82f6" label="SMA (20)" />
        <LegendItem color="#ec4899" label="SMA (50)" />
        <LegendItem color="#f59e0b" label="SMA (100)" />
        <LegendItem color="#22c55e" label="SMA (200)" dashed />
      </div>

      {/* Main candlestick chart */}
      <ResponsiveContainer width="100%" height={mainHeight}>
        <ComposedChart data={chartData} margin={{ top: 4, right: 70, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: TICK_COLOR, fontSize: 10 }}
            tickLine={false}
            axisLine={{ stroke: GRID_COLOR }}
            interval={step - 1}
            tickFormatter={fmtTick}
          />
          <YAxis
            orientation="right"
            tick={{ fill: TICK_COLOR, fontSize: 10 }}
            tickLine={false}
            axisLine={false}
            width={56}
            tickFormatter={fmtPrice}
          />
          <Tooltip
            content={<OhlcTooltip />}
            cursor={{ stroke: "#334155", strokeDasharray: "4 2", strokeWidth: 1 }}
          />

          {/* Candlestick / OHLC bars */}
          <Bar
            dataKey="range"
            shape={
              chartType === "ohlc"
                ? (p: object) => <OhlcShape {...(p as Parameters<typeof OhlcShape>[0])} />
                : (p: object) => <CandleShape {...(p as Parameters<typeof CandleShape>[0])} />
            }
            isAnimationActive={false}
          />

          {/* SMA lines */}
          <Line
            dataKey="sma20"
            stroke="#3b82f6"
            dot={false}
            strokeWidth={1.5}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            dataKey="sma50"
            stroke="#ec4899"
            dot={false}
            strokeWidth={1.5}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            dataKey="sma100"
            stroke="#f59e0b"
            dot={false}
            strokeWidth={1.5}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            dataKey="sma200"
            stroke="#22c55e"
            dot={false}
            strokeWidth={1.5}
            strokeDasharray="6 3"
            connectNulls
            isAnimationActive={false}
          />

          {/* Right-side MA labels via ReferenceLine */}
          {lastSma20 != null && (
            <ReferenceLine
              y={lastSma20}
              stroke="#3b82f6"
              strokeDasharray="2 4"
              strokeWidth={0.5}
              strokeOpacity={0.4}
              label={{
                value: `MA (20) ${lastSma20.toFixed(2)}`,
                position: "right",
                fill: "#3b82f6",
                fontSize: 9,
                fontWeight: 600,
              }}
            />
          )}
          {lastSma50 != null && (
            <ReferenceLine
              y={lastSma50}
              stroke="#ec4899"
              strokeDasharray="2 4"
              strokeWidth={0.5}
              strokeOpacity={0.4}
              label={{
                value: `MA (50) ${lastSma50.toFixed(2)}`,
                position: "right",
                fill: "#ec4899",
                fontSize: 9,
                fontWeight: 600,
              }}
            />
          )}
          {lastSma100 != null && (
            <ReferenceLine
              y={lastSma100}
              stroke="#f59e0b"
              strokeDasharray="2 4"
              strokeWidth={0.5}
              strokeOpacity={0.4}
              label={{
                value: `MA (100) ${lastSma100.toFixed(2)}`,
                position: "right",
                fill: "#f59e0b",
                fontSize: 9,
                fontWeight: 600,
              }}
            />
          )}
          {lastSma200 != null && (
            <ReferenceLine
              y={lastSma200}
              stroke="#22c55e"
              strokeDasharray="2 4"
              strokeWidth={0.5}
              strokeOpacity={0.4}
              label={{
                value: `MA (200) ${lastSma200.toFixed(2)}`,
                position: "right",
                fill: "#22c55e",
                fontSize: 9,
                fontWeight: 600,
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Volume panel */}
      <ResponsiveContainer width="100%" height={volHeight}>
        <ComposedChart data={chartData} margin={{ top: 0, right: 70, bottom: 4, left: 0 }}>
          <XAxis dataKey="date" hide />
          <YAxis
            orientation="right"
            tick={{ fill: TICK_COLOR, fontSize: 9 }}
            tickLine={false}
            axisLine={false}
            width={56}
            tickCount={2}
            tickFormatter={fmtVol}
          />
          <Bar
            dataKey="volume"
            shape={(p: object) => <VolumeBar {...(p as Parameters<typeof VolumeBar>[0])} />}
            isAnimationActive={false}
          />
          <text x={8} y={12} fontSize={9} fill="#6b7280" fontWeight={600}>
            Volume
          </text>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
};
