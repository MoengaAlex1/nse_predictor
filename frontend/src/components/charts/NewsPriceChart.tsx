import type { FC } from "react";
import { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { NewsItem } from "../../types";
import type { RtdbPricePoint } from "../../hooks/useHistoricalPrices";

interface Props {
  news: NewsItem[];
  rtdbPrices: RtdbPricePoint[];
}

interface DataPoint {
  date: string;
  title: string;
  category: string;
  pct: number;
  close: number | null;
}

const CATEGORY_DOT: Record<string, string> = {
  earnings:         "bg-emerald-500",
  dividend:         "bg-sky-500",
  regulatory:       "bg-amber-500",
  agm:              "bg-violet-500",
  corporate_action: "bg-orange-500",
  general:          "bg-slate-500",
};

const CustomTooltip = ({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: DataPoint }>;
}) => {
  if (!active || !payload?.[0]) return null;
  const d = payload[0].payload;
  const isUp = d.pct >= 0;
  return (
    <div className="max-w-[260px] rounded border border-rim bg-surface px-3 py-2.5 text-[11px] shadow-lg">
      <p className="mb-1 font-mono text-[10px] font-semibold text-muted">{d.date}</p>
      <div className="mb-1.5 flex items-start gap-1.5">
        <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${CATEGORY_DOT[d.category] ?? CATEGORY_DOT.general}`} />
        <p className="text-xs leading-snug text-ink">{d.title}</p>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[10px] text-muted">Price change:</span>
        <span className={`font-mono text-xs font-bold ${isUp ? "text-emerald-400" : "text-red-400"}`}>
          {isUp ? "+" : ""}
          {d.pct.toFixed(2)}%
        </span>
        {d.close != null && (
          <span className="font-mono text-[10px] text-hint">
            @ KES {d.close.toFixed(2)}
          </span>
        )}
      </div>
    </div>
  );
};

export const NewsPriceChart: FC<Props> = ({ news, rtdbPrices }) => {
  const data = useMemo<DataPoint[]>(() => {
    if (!news.length || !rtdbPrices.length) return [];

    const priceMap = new Map<string, RtdbPricePoint>(
      rtdbPrices.map((p) => [p.date, p]),
    );
    const tradingDates = rtdbPrices.map((p) => p.date).sort();

    const snapToTrading = (date: string): string | null => {
      if (priceMap.has(date)) return date;
      let best: string | null = null;
      let bestDiff = Infinity;
      const targetMs = new Date(date + "T00:00:00").getTime();
      for (const d of tradingDates) {
        const diff = Math.abs(new Date(d + "T00:00:00").getTime() - targetMs);
        if (diff < bestDiff && diff <= 5 * 86_400_000) {
          bestDiff = diff;
          best = d;
        }
      }
      return best;
    };

    const seen = new Set<string>();
    const points: DataPoint[] = [];

    const sorted = [...news].sort((a, b) => a.date.localeCompare(b.date));
    for (const item of sorted) {
      const snapDate = snapToTrading(item.date);
      if (!snapDate || seen.has(snapDate)) continue;
      seen.add(snapDate);

      const p = priceMap.get(snapDate);
      if (!p) continue;

      const pct =
        p.pch ??
        (p.ch != null && p.pc && p.pc > 0 ? (p.ch / p.pc) * 100 : null);
      if (pct == null) continue;

      points.push({
        date: snapDate,
        title: item.title,
        category: item.category,
        pct: Math.max(-15, Math.min(15, pct)),
        close: p.c,
      });
    }

    return points.slice(-40);
  }, [news, rtdbPrices]);

  if (data.length < 2) return null;

  const fmtDate = (d: string) => {
    const dt = new Date(d + "T00:00:00");
    return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  };

  const step = Math.max(1, Math.floor(data.length / 8));

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam/60 px-5 py-3">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          News Price Impact · % change on announcement day
        </p>
      </div>
      <div className="px-2 pb-3 pt-1">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart
            data={data}
            margin={{ top: 8, right: 16, left: 0, bottom: 4 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.05)"
              vertical={false}
            />
            <XAxis
              dataKey="date"
              tick={{ fill: "#475569", fontSize: 9 }}
              tickLine={false}
              axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              tickFormatter={fmtDate}
              interval={step - 1}
            />
            <YAxis
              orientation="right"
              tick={{ fill: "#475569", fontSize: 9 }}
              tickLine={false}
              axisLine={false}
              width={44}
              tickFormatter={(v) => `${v > 0 ? "+" : ""}${(v as number).toFixed(1)}%`}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
            />
            <ReferenceLine y={0} stroke="#334155" strokeWidth={1} />
            <Bar dataKey="pct" isAnimationActive={false} radius={[2, 2, 0, 0]}>
              {data.map((d, i) => (
                <Cell
                  key={i}
                  fill={d.pct >= 0 ? "#16a34a" : "#dc2626"}
                  opacity={0.8}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
