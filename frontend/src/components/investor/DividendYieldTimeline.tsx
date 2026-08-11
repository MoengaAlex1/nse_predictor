import { useMemo } from "react";
import type { FC } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";
import type { FinancialsDoc, DividendEvent, PricePoint } from "../../types";
import { EM_DASH } from "../../lib/format";

type Props = {
  financials: FinancialsDoc | null | undefined;
  priceHistory: PricePoint[];
  years?: number;    // default 10
  height?: number;   // default 200
};

type YieldRow = {
  year: string;
  yearNum: number;
  yieldPct: number | null;   // sum(dividends that year) / avg_price_that_year * 100
  divTotal: number;
  avgPrice: number | null;
};

function extractYear(d: DividendEvent): number | null {
  if (d.period) {
    const m = d.period.match(/(20\d{2}|19\d{2})/);
    if (m) return parseInt(m[1], 10);
  }
  if (d.period_end) {
    const y = d.period_end.slice(0, 4);
    if (/^\d{4}$/.test(y)) return parseInt(y, 10);
  }
  if (d.announcement_date) {
    return parseInt(d.announcement_date.slice(0, 4), 10);
  }
  return null;
}

function avgPriceForYear(history: PricePoint[], year: number): number | null {
  let sum = 0;
  let n = 0;
  for (const p of history) {
    if (p.date.slice(0, 4) === String(year) && p.price > 0) {
      sum += p.price;
      n += 1;
    }
  }
  return n > 0 ? sum / n : null;
}

export const DividendYieldTimeline: FC<Props> = ({
  financials,
  priceHistory,
  years = 10,
  height = 200,
}) => {
  const rows = useMemo<YieldRow[]>(() => {
    // Sum cash dividends per year.
    const totalByYear = new Map<number, number>();
    for (const d of financials?.dividends ?? []) {
      if (d.amount_kes == null || d.amount_kes <= 0) continue;
      if (d.type === "scrip" || d.type === "bonus" || d.type === "none") continue;
      const y = extractYear(d);
      if (y == null) continue;
      totalByYear.set(y, (totalByYear.get(y) ?? 0) + d.amount_kes);
    }
    if (totalByYear.size === 0) return [];

    const sortedYears = Array.from(totalByYear.keys()).sort((a, b) => a - b);
    const result: YieldRow[] = [];
    for (const y of sortedYears) {
      const divTotal = totalByYear.get(y)!;
      const avgPrice = avgPriceForYear(priceHistory, y);
      const yieldPct = avgPrice != null && avgPrice > 0 ? (divTotal / avgPrice) * 100 : null;
      result.push({ year: `FY${y}`, yearNum: y, yieldPct, divTotal, avgPrice });
    }
    return result.slice(-years);
  }, [financials?.dividends, priceHistory, years]);

  const avgYield = useMemo(() => {
    const nums = rows.map((r) => r.yieldPct).filter((v): v is number => v != null);
    if (nums.length === 0) return null;
    return nums.reduce((a, b) => a + b, 0) / nums.length;
  }, [rows]);

  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Yield Timeline
        </p>
        <p className="mt-3 text-xs text-hint">
          Yield history needs both dividend amounts and matching-year price
          history. Populates once the daily bulletin scraper finds cash
          dividends for years with recorded prices.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Yield Timeline
        </p>
        <span className="font-mono text-[10px] text-hint">
          {avgYield != null ? `Avg ${avgYield.toFixed(2)}%` : "—"} · dividend ÷ avg price
        </span>
      </div>
      <div className="px-3 pb-2 pt-3" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="rgb(var(--seam))" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="year"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "rgb(var(--hint))", fontSize: 10 }}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: "rgb(var(--hint))", fontSize: 10 }}
              width={40}
              tickFormatter={(v: number) => `${v.toFixed(1)}%`}
            />
            {avgYield != null && (
              <ReferenceLine
                y={avgYield}
                stroke="rgb(var(--hint))"
                strokeDasharray="3 3"
                strokeWidth={1}
              />
            )}
            <Tooltip content={<YieldTooltip />} cursor={{ stroke: "#38bdf8", strokeDasharray: "3 3" }} />
            <Line
              type="monotone"
              dataKey="yieldPct"
              stroke="#38bdf8"
              strokeWidth={2}
              dot={{ r: 3, fill: "#38bdf8" }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const YieldTooltip: FC<{
  active?: boolean;
  payload?: { payload: YieldRow }[];
}> = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded-md border border-rim bg-surface px-2.5 py-1.5 text-xs shadow-lg">
      <p className="font-mono text-[10px] font-semibold text-ink">{r.year}</p>
      <p className="mt-0.5 font-mono text-[10px] text-sky-400">
        Yield {r.yieldPct != null ? `${r.yieldPct.toFixed(2)}%` : EM_DASH}
      </p>
      <p className="font-mono text-[10px] text-hint">
        KES {r.divTotal.toFixed(2)}/share · avg KES{" "}
        {r.avgPrice != null ? r.avgPrice.toFixed(2) : EM_DASH}
      </p>
    </div>
  );
};
