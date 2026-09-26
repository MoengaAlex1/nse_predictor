import { useState } from "react";
import type { FC } from "react";
import type { SnapshotDoc } from "../../types";
import { PredictionChart, HORIZON_OPTIONS } from "../charts/PredictionChart";

// Extracted from CompanyDeepDive so InvestorChart (the canonical
// company page after the /company → /chart merge) can render it.
// User feedback: "the prediction model cannot see it" — root cause was
// this panel being defined inline in CompanyDeepDive and never
// imported by the merged InvestorChart page.
export const ForecastPanel: FC<{ snapshot: SnapshotDoc }> = ({ snapshot }) => {
  const [horizonKey, setHorizonKey] = useState<string>("1M");
  const active = HORIZON_OPTIONS.find(o => o.key === horizonKey) ?? HORIZON_OPTIONS[0];
  const hasLong = !!snapshot.forecast_long?.length;
  const mhPred = snapshot.horizon_predictions?.[horizonKey] ?? null;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-[#0d1117]">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Actual vs Model · Forecast
          </h2>
          <p className="mt-0.5 text-[10px] text-slate-600">
            Dashed line = today · Green zone = forward projection
            {hasLong && active.days > 30 && (
              <span> · Past day 30 uses ARIMA-only (LSTM accuracy degrades past ~10 bars)</span>
            )}
            {mhPred && (
              <span> · LightGBM point estimate uses earnings + announcements + technicals</span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          {HORIZON_OPTIONS.map(opt => {
            const enabled = hasLong || opt.days <= 30;
            const activeCls = opt.key === horizonKey
              ? "bg-emerald-600 text-white"
              : enabled
                ? "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
                : "text-slate-700 cursor-not-allowed";
            return (
              <button
                key={opt.key}
                type="button"
                disabled={!enabled}
                onClick={() => enabled && setHorizonKey(opt.key)}
                className={`rounded px-2 py-1 text-[11px] font-semibold transition-colors ${activeCls}`}
                title={enabled ? opt.label : "Requires a fresh snapshot with forecast_long"}
              >
                {opt.key}
              </button>
            );
          })}
        </div>
      </div>

      {mhPred && (
        <div className="flex flex-wrap items-baseline gap-4 border-b border-slate-800 px-4 py-2.5 text-[11px]">
          <span className="uppercase tracking-wider text-slate-500">
            {horizonKey} target
          </span>
          <span className="font-mono text-base font-semibold text-slate-100">
            KES {mhPred.target_price.toFixed(2)}
          </span>
          <span
            className={`font-mono font-semibold ${
              mhPred.pct_return >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {mhPred.pct_return >= 0 ? "+" : ""}
            {mhPred.pct_return.toFixed(2)}%
          </span>
          <span className="text-slate-500">
            over {mhPred.horizon_days} trading days
          </span>
          {mhPred.mape != null && (
            <span
              className="ml-auto rounded border border-slate-700 bg-slate-800/60 px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
              title={`Walk-forward backtest on unseen recent history. Avg error ${mhPred.mape.toFixed(1)}pp on horizon return${mhPred.direction_hit != null ? `; ${(mhPred.direction_hit * 100).toFixed(0)}% direction hit rate (up/down correct)` : ""}.`}
            >
              ±{mhPred.mape.toFixed(1)}pp
              {mhPred.direction_hit != null && (
                <span> · direction hit {(mhPred.direction_hit * 100).toFixed(0)}%</span>
              )}
            </span>
          )}
        </div>
      )}

      <div className="px-1 pb-3 pt-1">
        <PredictionChart
          actuals={snapshot.actuals}
          preds={snapshot.preds}
          forecast={snapshot.forecast}
          runDate={snapshot.run_date}
          forecastDates={snapshot.forecast_dates}
          forecastLong={snapshot.forecast_long}
          forecastLongDates={snapshot.forecast_long_dates}
          lstmBoundaryDay={snapshot.forecast_lstm_boundary_day ?? 30}
          horizonDays={active.days}
        />
      </div>
    </div>
  );
};
