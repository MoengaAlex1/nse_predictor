import { useMemo } from "react";
import type { FC } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell, Legend,
} from "recharts";
import type { FinancialsDoc, DividendEvent } from "../../types";
import { EM_DASH } from "../../lib/format";

type Props = {
  financials: FinancialsDoc | null | undefined;
  years?: number;   // default 10
  height?: number;  // default 220
};

type Bucket = {
  year: string;
  yearNum: number;
  final: number;
  interim: number;
  special: number;
  total: number;
  count: number;
};

const TYPE_COLORS: Record<string, string> = {
  final:   "#22c55e",  // emerald
  interim: "#38bdf8",  // sky
  special: "#f59e0b",  // amber
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

export const DividendHistoryChart: FC<Props> = ({ financials, years = 10, height = 220 }) => {
  const buckets = useMemo<Bucket[]>(() => {
    const map = new Map<number, Bucket>();
    for (const d of financials?.dividends ?? []) {
      if (d.amount_kes == null || d.amount_kes <= 0) continue;
      // Skip stock-based dividends
      if (d.type === "scrip" || d.type === "bonus" || d.type === "none") continue;
      const y = extractYear(d);
      if (y == null) continue;
      const b = map.get(y) ?? {
        year: `FY${y}`, yearNum: y, final: 0, interim: 0, special: 0, total: 0, count: 0,
      };
      if (d.type === "final") b.final += d.amount_kes;
      else if (d.type === "interim") b.interim += d.amount_kes;
      else if (d.type === "special") b.special += d.amount_kes;
      else b.final += d.amount_kes; // fallback bucket
      b.total += d.amount_kes;
      b.count += 1;
      map.set(y, b);
    }
    return Array.from(map.values())
      .sort((a, b) => a.yearNum - b.yearNum)
      .slice(-years);
  }, [financials?.dividends, years]);

  if (buckets.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Dividend History
        </p>
        <p className="mt-3 text-xs text-hint">
          No dividend records with an amount recorded yet. Dividends land here as
          the NSE daily-bulletin scraper OCRs new PDFs (Saturday 06:00 UTC).
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Dividend History
        </p>
        <span className="font-mono text-[10px] text-hint">
          {buckets[0].year} → {buckets[buckets.length - 1].year} · KES/share per year
        </span>
      </div>
      <div className="px-3 pb-2 pt-3" style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={buckets} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
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
              tickFormatter={(v: number) => v.toFixed(1)}
            />
            <Tooltip content={<DivTooltip />} cursor={{ fill: "rgb(var(--seam))", opacity: 0.25 }} />
            <Legend
              iconType="square"
              wrapperStyle={{ fontSize: 10, color: "rgb(var(--hint))" }}
            />
            <Bar dataKey="final" stackId="d" name="Final" fill={TYPE_COLORS.final}>
              {buckets.map((_, i) => <Cell key={i} />)}
            </Bar>
            <Bar dataKey="interim" stackId="d" name="Interim" fill={TYPE_COLORS.interim} />
            <Bar dataKey="special" stackId="d" name="Special" fill={TYPE_COLORS.special} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

const DivTooltip: FC<{
  active?: boolean;
  payload?: { payload: Bucket }[];
}> = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const b = payload[0].payload;
  return (
    <div className="rounded-md border border-rim bg-surface px-2.5 py-1.5 text-xs shadow-lg">
      <p className="font-mono text-[10px] font-semibold text-ink">{b.year}</p>
      <div className="mt-1 space-y-0.5 font-mono text-[10px]">
        {b.final > 0 && (
          <p style={{ color: TYPE_COLORS.final }}>Final&nbsp;&nbsp;&nbsp;KES {b.final.toFixed(2)}</p>
        )}
        {b.interim > 0 && (
          <p style={{ color: TYPE_COLORS.interim }}>Interim&nbsp;&nbsp;KES {b.interim.toFixed(2)}</p>
        )}
        {b.special > 0 && (
          <p style={{ color: TYPE_COLORS.special }}>Special&nbsp;&nbsp;KES {b.special.toFixed(2)}</p>
        )}
        <p className="border-t border-seam pt-1 text-ink">
          Total&nbsp;&nbsp;&nbsp;&nbsp;KES {b.total > 0 ? b.total.toFixed(2) : EM_DASH}
        </p>
        <p className="text-hint">{b.count} announcement{b.count === 1 ? "" : "s"}</p>
      </div>
    </div>
  );
};
