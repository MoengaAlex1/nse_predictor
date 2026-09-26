import type { FC } from "react";
import { fmtShort, fmtMedium, tradingDaysFrom } from "../../lib/dateUtils";
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
  forecastDates?: string[];
  /** Long ARIMA-only forecast (up to 252 trading days ≈ 12 months) —
   *  used when the caller selects a horizon > 30 days. Falls back to the
   *  30-day `forecast` array when absent. */
  forecastLong?: number[];
  forecastLongDates?: string[];
  /** Day (1-indexed) at which the blended LSTM+ARIMA forecast stops and
   *  ARIMA-only takes over. Draws a vertical marker so the reader knows
   *  where model confidence changes. Defaults to 30. */
  lstmBoundaryDay?: number;
  /** Horizon (in trading days) to display. Passed by the horizon selector. */
  horizonDays?: number;
}

const fmtFull = fmtMedium;

export const PredictionChart: FC<Props> = ({
  actuals,
  preds,
  forecast,
  runDate,
  forecastDates,
  forecastLong,
  forecastLongDates,
  lstmBoundaryDay = 30,
  horizonDays,
}) => {
  const n = Math.min(actuals.length, preds.length);
  const ref = new Date(runDate + "T00:00:00");

  // Pick the forecast series that best fits the requested horizon.
  // If the caller didn't provide horizonDays, use the 30-day series so
  // existing render paths keep their behavior.
  const wantHorizon = horizonDays ?? 30;
  const useLong = wantHorizon > 30 && forecastLong && forecastLong.length > 30;
  const rawForecast = useLong ? forecastLong! : forecast;
  const rawForecastDates = useLong
    ? (forecastLongDates ?? forecast.map((_, i) => tradingDaysFrom(ref, i + 1)))
    : (forecastDates ?? forecast.map((_, i) => tradingDaysFrom(ref, i + 1)));
  const trimmedForecast = rawForecast.slice(0, wantHorizon);
  const trimmedDates = rawForecastDates.slice(0, wantHorizon);

  const histData = Array.from({ length: n }, (_, i) => ({
    date: tradingDaysFrom(ref, -(n - 1 - i)),
    actual: actuals[i],
    predicted: preds[i],
  }));

  const forecastData = trimmedForecast.map((v, i) => ({
    date: trimmedDates[i] ?? tradingDaysFrom(ref, i + 1),
    forecast: v,
    actual: undefined,
    predicted: undefined,
  }));

  const allData = [...histData, ...forecastData];
  const totalLen = allData.length;
  const step = Math.max(1, Math.floor(totalLen / 8));

  // Position the LSTM-boundary marker on the x-axis if we're rendering a
  // horizon that reaches past it. Signals "past this date the forecast
  // is ARIMA-only" so the reader isn't misled by the same green fill.
  const boundaryDate = wantHorizon > lstmBoundaryDay
    ? (trimmedDates[lstmBoundaryDay - 1] ?? null)
    : null;

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
        {boundaryDate && (
          <ReferenceLine
            x={boundaryDate}
            stroke="#facc15"
            strokeDasharray="2 2"
            label={{ value: "ARIMA only →", position: "top", fill: "#facc15", fontSize: 10 }}
          />
        )}
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
          name={useLong ? `Forecast (${horizonLabelFor(wantHorizon)})` : "Forecast (30d)"}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
};

// Trading-day counts → human labels for the legend and any parent
// button/chip that wants to keep the mapping in one place.
export const HORIZON_OPTIONS: { key: string; label: string; days: number }[] = [
  { key: "1M",  label: "1 month",   days: 21  },
  { key: "3M",  label: "3 months",  days: 63  },
  { key: "6M",  label: "6 months",  days: 126 },
  { key: "9M",  label: "9 months",  days: 189 },
  { key: "12M", label: "12 months", days: 252 },
];

function horizonLabelFor(days: number): string {
  const opt = HORIZON_OPTIONS.find(o => o.days === days);
  return opt?.key ?? `${days}d`;
}
