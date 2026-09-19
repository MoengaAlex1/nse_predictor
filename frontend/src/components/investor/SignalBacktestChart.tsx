import type { FC } from "react";
import { useMemo } from "react";
import {
  Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Scatter, ComposedChart, ReferenceLine,
} from "recharts";
import type { SnapshotDoc, PricePoint } from "../../types";

interface Props {
  snapshots: SnapshotDoc[] | undefined;
  history: PricePoint[];
  /** Cap the chart window to the last N calendar days. Defaults to 180 (~6 months). */
  windowDays?: number;
}

interface Row {
  date: string;
  price: number | null;
  buyMarker?: number;
  sellMarker?: number;
  holdMarker?: number;
}

/**
 * Plots historical price with dot overlays where the model called BUY / SELL
 * / HOLD, so users can eyeball whether the signals landed at good moments.
 *
 * Reads snapshots (latest first) and marks each call at its `run_date` on the
 * price line. Green dot = BUY, red = SELL, amber = HOLD. Only rendered when
 * there are at least a few scored calls in the window — otherwise there's
 * nothing meaningful to eyeball yet.
 */
export const SignalBacktestChart: FC<Props> = ({ snapshots, history, windowDays = 180 }) => {
  const rows: Row[] = useMemo(() => {
    if (!history.length) return [];
    const cutoff = (() => {
      const d = new Date();
      d.setDate(d.getDate() - windowDays);
      return d.toISOString().slice(0, 10);
    })();

    // Index snapshots by run_date so we can attach markers to matching bars.
    const byDate = new Map<string, SnapshotDoc>();
    (snapshots ?? []).forEach(s => {
      if (s.run_date >= cutoff) byDate.set(s.run_date, s);
    });

    return history
      .filter(p => p.date >= cutoff)
      .map(p => {
        const snap = byDate.get(p.date);
        const row: Row = { date: p.date, price: p.price };
        if (snap) {
          const sig = snap.risk_adjusted_signal;
          if (sig === "BUY")  row.buyMarker  = p.price;
          if (sig === "SELL") row.sellMarker = p.price;
          if (sig === "HOLD") row.holdMarker = p.price;
        }
        return row;
      });
  }, [snapshots, history, windowDays]);

  const markerCount = useMemo(
    () => rows.filter(r => r.buyMarker != null || r.sellMarker != null || r.holdMarker != null).length,
    [rows],
  );

  if (rows.length < 5) {
    return null;
  }

  if (markerCount < 2) {
    return (
      <div className="rounded-xl border border-rim bg-surface px-5 py-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Signal Backtest · past {windowDays}d
        </p>
        <p className="mt-2 text-sm text-hint">
          Not enough historical signals to plot yet — the backtest needs at least
          two past calls in the window. Once the daily inference has been running
          for a few weeks, this chart will show each BUY/SELL/HOLD call over
          price so you can see whether the model timed moves well.
        </p>
      </div>
    );
  }

  const [firstPrice, lastPrice] = [rows[0].price ?? 0, rows[rows.length - 1].price ?? 0];
  const overallPct = firstPrice > 0 ? ((lastPrice - firstPrice) / firstPrice) * 100 : 0;
  const isUp = overallPct >= 0;

  return (
    <div className="rounded-xl border border-rim bg-surface px-5 py-4 space-y-3">
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Signal Backtest · past {windowDays}d
        </p>
        <p className="text-[10px] text-hint">
          {markerCount} call{markerCount === 1 ? "" : "s"} · price{" "}
          <span className={isUp ? "text-emerald-500" : "text-red-500"}>
            {isUp ? "▲" : "▼"} {Math.abs(overallPct).toFixed(1)}%
          </span>{" "}
          over window
        </p>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer>
          <ComposedChart data={rows} margin={{ top: 5, right: 12, bottom: 0, left: -8 }}>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "rgb(var(--hint))" }}
              tickFormatter={(d: string) => d.slice(5)}
              minTickGap={40}
            />
            <YAxis
              tick={{ fontSize: 10, fill: "rgb(var(--hint))" }}
              domain={["dataMin", "dataMax"]}
              tickFormatter={(v: number) => v.toFixed(0)}
              width={44}
            />
            <Tooltip
              contentStyle={{
                background: "rgb(var(--surface))",
                border: "1px solid rgb(var(--rim))",
                fontSize: 12,
              }}
              formatter={(value, name) => {
                const v = typeof value === "number" ? value : Number(value ?? 0);
                if (name === "price") return [`KES ${v.toFixed(2)}`, "Close"];
                if (name === "buyMarker")  return [`BUY at KES ${v.toFixed(2)}`, "Signal"];
                if (name === "sellMarker") return [`SELL at KES ${v.toFixed(2)}`, "Signal"];
                if (name === "holdMarker") return [`HOLD at KES ${v.toFixed(2)}`, "Signal"];
                return [String(value), String(name)];
              }}
            />
            <ReferenceLine y={firstPrice} stroke="rgb(var(--seam))" strokeDasharray="2 4" />
            <Line
              type="monotone"
              dataKey="price"
              stroke="rgb(var(--accent))"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Scatter dataKey="buyMarker"  fill="#10b981" shape="circle" />
            <Scatter dataKey="sellMarker" fill="#ef4444" shape="circle" />
            <Scatter dataKey="holdMarker" fill="#f59e0b" shape="circle" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-[10px] text-hint">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" /> BUY
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-red-500" /> SELL
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-2 w-2 rounded-full bg-amber-500" /> HOLD
        </span>
        <span className="text-hint">
          · Dots plot at each signal's run_date; use to eyeball timing quality
        </span>
      </div>
    </div>
  );
};
