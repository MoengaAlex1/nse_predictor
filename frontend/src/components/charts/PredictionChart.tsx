import type { FC } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

interface Props {
  actuals: number[];
  preds: number[];
  forecast: number[];
  runDate: string;
}

function tradingDaysFrom(base: Date, offset: number): string {
  const d = new Date(base);
  let remaining = Math.abs(offset);
  const direction = offset >= 0 ? 1 : -1;
  while (remaining > 0) {
    d.setDate(d.getDate() + direction);
    const day = d.getDay();
    if (day !== 0 && day !== 6) remaining--;
  }
  return d.toISOString().slice(0, 10);
}

const fmtShort = (dateStr: string) => {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-KE", { month: "short", day: "numeric" });
};

const fmtFull = (dateStr: string) =>
  new Date(dateStr + "T00:00:00").toLocaleDateString("en-KE", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

export const PredictionChart: FC<Props> = ({ actuals, preds, forecast, runDate }) => {
  const n = Math.min(actuals.length, preds.length);
  const ref = new Date(runDate + "T00:00:00");

  const histData = Array.from({ length: n }, (_, i) => ({
    date: tradingDaysFrom(ref, -(n - 1 - i)),
    actual: actuals[i],
    predicted: preds[i],
  }));

  const forecastData = forecast.map((v, i) => ({
    date: tradingDaysFrom(ref, i + 1),
    forecast: v,
    actual: undefined,
    predicted: undefined,
  }));

  const allData = [...histData, ...forecastData];
  const totalLen = allData.length;
  const step = Math.max(1, Math.floor(totalLen / 8));

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={allData} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
        <defs>
          <linearGradient id="forecast-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#34d399" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#34d399" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
        <XAxis
          dataKey="date"
          tick={{ fill: "#64748b", fontSize: 11 }}
          tickLine={false}
          tickFormatter={fmtShort}
          interval={step - 1}
        />
        <YAxis
          tickFormatter={(v: number) =>
            v >= 1000 ? `${(v / 1000).toFixed(1)}k` : v.toFixed(2)
          }
          tick={{ fill: "#64748b", fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={60}
        />
        <Tooltip
          contentStyle={{
            background: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelFormatter={(label) => fmtFull(String(label))}
          formatter={(v, name) => [
            v != null ? `KES ${Number(v).toFixed(2)}` : "—",
            name,
          ]}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, color: "#94a3b8", paddingTop: 8 }}
        />
        <ReferenceLine x={runDate} stroke="#475569" strokeDasharray="4 2" />
        <Line
          type="monotone"
          dataKey="actual"
          stroke="#38bdf8"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 3 }}
          name="Actual"
        />
        <Line
          type="monotone"
          dataKey="predicted"
          stroke="#a78bfa"
          strokeWidth={2}
          dot={false}
          strokeDasharray="5 3"
          activeDot={{ r: 3 }}
          name="Model (test)"
        />
        <Area
          type="monotone"
          dataKey="forecast"
          stroke="#34d399"
          fill="url(#forecast-grad)"
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 3 }}
          name="Forecast (30d)"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
};
