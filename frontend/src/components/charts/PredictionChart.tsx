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
  ResponsiveContainer,
} from "recharts";

interface Props {
  actuals: number[];
  preds: number[];
  forecast: number[];
}

export const PredictionChart: FC<Props> = ({ actuals, preds, forecast }) => {
  const n = Math.min(actuals.length, preds.length);

  const histData = Array.from({ length: n }, (_, i) => ({
    i,
    actual: actuals[i],
    predicted: preds[i],
  }));

  const forecastData = forecast.map((v, i) => ({
    i: n + i,
    forecast: v,
    actual: undefined,
    predicted: undefined,
  }));

  const allData = [...histData, ...forecastData];

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={allData}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis dataKey="i" tick={false} />
        <YAxis
          tickFormatter={(v: number) => v.toFixed(0)}
          tick={{ fill: "#94a3b8", fontSize: 11 }}
          width={55}
        />
        <Tooltip
          contentStyle={{
            background: "#1e293b",
            border: "1px solid #334155",
            borderRadius: 8,
            fontSize: 12,
          }}
          formatter={(v: number, name: string) => [
            `KES ${v?.toFixed(2) ?? "—"}`,
            name,
          ]}
        />
        <Legend />
        <Line
          type="monotone"
          dataKey="actual"
          stroke="#38bdf8"
          strokeWidth={2}
          dot={false}
          name="Actual"
        />
        <Line
          type="monotone"
          dataKey="predicted"
          stroke="#a78bfa"
          strokeWidth={2}
          dot={false}
          strokeDasharray="4 2"
          name="Predicted"
        />
        <Area
          type="monotone"
          dataKey="forecast"
          stroke="#34d399"
          fill="#34d39920"
          strokeWidth={2}
          dot={false}
          name="Forecast"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
};
