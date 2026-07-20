import { useState } from "react";
import type { FC } from "react";
import { useParams, Link } from "react-router-dom";
import { fmtDate } from "../lib/dateUtils";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { CompanyLogo } from "../components/ui/CompanyLogo";
import { SparkLine } from "../components/charts/SparkLine";
import { PredictionChart } from "../components/charts/PredictionChart";
import { useCompany, useLatestSnapshot, useLatestTechnicals } from "../hooks/useCompany";
import type { PricePoint, SnapshotDoc, TechnicalsDoc } from "../types";

type RangeKey = "1M" | "3M" | "6M" | "1Y" | "ALL" | "Custom";

const PRESETS: { label: RangeKey; days: number | null }[] = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
  { label: "ALL", days: null },
  { label: "Custom", days: null },
];

function filterByRange(
  data: PricePoint[],
  range: RangeKey,
  customFrom: string,
  customTo: string,
): PricePoint[] {
  if (data.length === 0) return data;
  if (range === "Custom") {
    return data.filter(
      (p) => (!customFrom || p.date >= customFrom) && (!customTo || p.date <= customTo),
    );
  }
  const days = PRESETS.find((r) => r.label === range)?.days ?? null;
  if (!days) return data;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  return data.filter((p) => p.date >= cutoff.toISOString().slice(0, 10));
}


export const CompanyDeepDive: FC = () => {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const { data: company, isLoading, isError } = useCompany(ticker);
  const [range, setRange] = useState<RangeKey>("3M");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");

  if (isLoading) {
    return (
      <PageShell>
        <div className="flex justify-center py-16">
          <Spinner size="lg" />
        </div>
      </PageShell>
    );
  }

  if (isError || !company) {
    return (
      <PageShell>
        <Card className="border-red-800">
          <p className="text-red-400">Company not found.</p>
          <Link to="/companies" className="mt-2 block text-sm text-sky-400 hover:underline">
            ← Back to companies
          </Link>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-3">
              <CompanyLogo
                id={ticker}
                short={company.short}
                color={company.color}
                icon={company.icon}
                size="lg"
              />
              <h1 className="text-3xl font-bold text-slate-100">{company.name}</h1>
              {company.signal && <SignalBadge signal={company.signal} size="lg" />}
            </div>
            <p className="mt-1 text-slate-400">
              {company.sector} · {company.ticker}
            </p>
          </div>
          <div className="text-right">
            {company.current_price !== null && (
              <>
                <p className="text-3xl font-bold text-slate-100">
                  KES {company.current_price.toFixed(2)}
                </p>
                {company.change_pct_today !== null && (
                  <p
                    className={`text-sm font-medium ${
                      company.change_pct_today >= 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {company.change_pct_today >= 0 ? "+" : ""}
                    {company.change_pct_today.toFixed(2)}% today
                  </p>
                )}
                {company.last_updated && (
                  <p className="mt-1 text-xs text-slate-500">
                    Data as of {fmtDate(company.last_updated)}
                  </p>
                )}
              </>
            )}
          </div>
        </div>

        {/* Historical price chart */}
        {company.price_history?.length > 0 ? (
          <PriceHistoryCard
            priceHistory={company.price_history}
            color={company.color}
            range={range}
            onRangeChange={setRange}
            customFrom={customFrom}
            customTo={customTo}
            onCustomFromChange={setCustomFrom}
            onCustomToChange={setCustomTo}
          />
        ) : company.price_preview.length > 0 ? (
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                30-Day Price Trend
              </h2>
              <span className="text-xs text-slate-500">
                Re-seed pipeline for exact trading-day dates
              </span>
            </div>
            <SparkLine
              data={(() => {
                const ref = company.last_updated
                  ? new Date(company.last_updated + "T00:00:00")
                  : new Date();
                while (ref.getDay() === 0 || ref.getDay() === 6) {
                  ref.setDate(ref.getDate() - 1);
                }
                const n = company.price_preview.length;
                const tradingDates: string[] = [];
                const cursor = new Date(ref);
                while (tradingDates.length < n) {
                  const day = cursor.getDay();
                  if (day !== 0 && day !== 6) {
                    tradingDates.unshift(cursor.toISOString().slice(0, 10));
                  }
                  cursor.setDate(cursor.getDate() - 1);
                }
                return company.price_preview.map((price, i) => ({
                  date: tradingDates[i],
                  price,
                }));
              })()}
              color={company.color}
            />
          </Card>
        ) : null}

        <GatedContent ticker={ticker} />
      </div>
    </PageShell>
  );
};

const RangeButton: FC<{ label: RangeKey; active: boolean; onClick: () => void }> = ({
  label,
  active,
  onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
      active
        ? "bg-sky-600 text-white"
        : "text-slate-400 hover:bg-slate-700 hover:text-slate-200"
    }`}
  >
    {label}
  </button>
);

const PriceHistoryCard: FC<{
  priceHistory: PricePoint[];
  color: string;
  range: RangeKey;
  onRangeChange: (r: RangeKey) => void;
  customFrom: string;
  customTo: string;
  onCustomFromChange: (v: string) => void;
  onCustomToChange: (v: string) => void;
}> = ({ priceHistory, color, range, onRangeChange, customFrom, customTo, onCustomFromChange, onCustomToChange }) => {
  const visible = filterByRange(priceHistory, range, customFrom, customTo);
  const first = visible[0]?.date ?? "—";
  const last = visible[visible.length - 1]?.date ?? "—";
  const dataMin = priceHistory[0]?.date ?? "";
  const dataMax = priceHistory[priceHistory.length - 1]?.date ?? "";

  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Price History
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            {first} → {last} · {visible.length} trading days
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1 rounded-lg bg-slate-800 p-1">
            {PRESETS.map((r) => (
              <RangeButton
                key={r.label}
                label={r.label}
                active={range === r.label}
                onClick={() => onRangeChange(r.label)}
              />
            ))}
          </div>
          {range === "Custom" && (
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={customFrom}
                min={dataMin}
                max={customTo || dataMax}
                onChange={(e) => onCustomFromChange(e.target.value)}
                className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
              />
              <span className="text-xs text-slate-500">to</span>
              <input
                type="date"
                value={customTo}
                min={customFrom || dataMin}
                max={dataMax}
                onChange={(e) => onCustomToChange(e.target.value)}
                className="rounded border border-slate-600 bg-slate-800 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
              />
            </div>
          )}
        </div>
      </div>
      <SparkLine data={visible} color={color} />
    </Card>
  );
};

const GatedContent: FC<{ ticker: string }> = ({ ticker }) => {
  const { data: snapshot, isLoading: snapLoading } = useLatestSnapshot(ticker);
  const { data: technicals, isLoading: techLoading } = useLatestTechnicals(ticker);

  if (snapLoading || techLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {snapshot ? (
        <SnapshotSection snapshot={snapshot} />
      ) : (
        <Card>
          <p className="text-slate-400">
            No prediction data yet. Pipeline runs daily at 18:00 EAT.
          </p>
        </Card>
      )}

      {snapshot && snapshot.actuals.length > 0 && (
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
              Actual vs Model Prediction
            </h2>
            <span className="text-xs text-slate-500">
              Dashed line = today · Green shading = 30-day forecast
            </span>
          </div>
          <PredictionChart
            actuals={snapshot.actuals}
            preds={snapshot.preds}
            forecast={snapshot.forecast}
            runDate={snapshot.run_date}
            forecastDates={snapshot.forecast_dates}
          />
        </Card>
      )}

      {technicals && <TechnicalsSection technicals={technicals} />}
    </div>
  );
};

const signalBulletColor: Record<string, string> = {
  BUY: "text-emerald-400",
  HOLD: "text-amber-400",
  SELL: "text-red-400",
};

const confidenceBarColor = (score: number) =>
  score >= 70 ? "bg-emerald-500" : score >= 45 ? "bg-amber-500" : "bg-red-500";

const SnapshotSection: FC<{ snapshot: SnapshotDoc }> = ({ snapshot }) => {
  const sig = snapshot.risk_adjusted_signal;
  const bulletColor = signalBulletColor[sig] ?? "text-slate-400";

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">AI Signal</h2>
        <span className="text-xs text-slate-500">Analysis run: {fmtDate(snapshot.run_date)}</span>
      </div>

      <div className="mb-4 rounded-lg border border-sky-800/40 bg-sky-900/20 px-4 py-2">
        <p className="text-xs uppercase tracking-wider text-sky-400/70">Prediction target</p>
        <p className="text-sm font-semibold text-sky-300">{fmtDate(snapshot.next_trading_day)}</p>
      </div>

      {/* Hero: signal + confidence + price */}
      <div className="mb-6 flex flex-wrap items-start gap-6">
        <div className="flex flex-col items-center gap-2">
          <SignalBadge signal={sig} size="lg" />
          <span className="text-xs text-slate-500">Risk-Adjusted</span>
          {snapshot.signal !== sig && (
            <>
              <SignalBadge signal={snapshot.signal} size="sm" />
              <span className="text-xs text-slate-600">Raw</span>
            </>
          )}
        </div>
        <div className="flex flex-1 flex-col gap-4">
          {snapshot.confidence_score !== undefined && (
            <div>
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs text-slate-500">Confidence</span>
                <span className="text-xs font-semibold text-slate-300">
                  {snapshot.confidence_score}%
                </span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className={`h-2 rounded-full transition-all ${confidenceBarColor(snapshot.confidence_score)}`}
                  style={{ width: `${snapshot.confidence_score}%` }}
                />
              </div>
            </div>
          )}
          <div className="flex flex-wrap gap-6">
            <Metric
              label={`Predicted Close (${snapshot.next_trading_day})`}
              value={
                <span className="text-xl font-bold text-slate-100">
                  KES {snapshot.predicted_price_KES.toFixed(2)}
                </span>
              }
            />
            <Metric
              label="Expected Move"
              value={
                <span
                  className={`text-xl font-bold ${
                    snapshot.predicted_change_pct >= 0 ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  {snapshot.predicted_change_pct >= 0 ? "+" : ""}
                  {snapshot.predicted_change_pct.toFixed(2)}%
                </span>
              }
            />
          </div>
        </div>
      </div>

      {/* Why this signal */}
      {snapshot.signal_reasons && snapshot.signal_reasons.length > 0 && (
        <div className="mb-4 rounded-lg border border-slate-700 bg-slate-900/50 p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Why this signal
          </h3>
          <ul className="space-y-2">
            {snapshot.signal_reasons.map((reason, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <span className={`mt-0.5 shrink-0 font-bold ${bulletColor}`}>•</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* What this means for you */}
      {snapshot.signal_implications && (
        <div className="mb-4 rounded-lg border border-slate-700 bg-slate-900/50 p-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
            What this means for you
          </h3>
          <p className="text-sm leading-relaxed text-slate-300">{snapshot.signal_implications}</p>
        </div>
      )}

      {/* Rationale */}
      <p className="mt-2 text-sm text-slate-400">{snapshot.rationale}</p>

      {/* Model breakdown table */}
      {snapshot.model_breakdown && Object.keys(snapshot.model_breakdown).length > 0 && (
        <div className="mt-5">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Model Breakdown
          </h3>
          <div className="overflow-hidden rounded-lg border border-slate-700">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-800">
                  <th className="px-3 py-2 text-left text-xs font-medium text-slate-500">Model</th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-slate-500">
                    Predicted Price
                  </th>
                  <th className="px-3 py-2 text-right text-xs font-medium text-slate-500">
                    Change
                  </th>
                  <th className="px-3 py-2 text-center text-xs font-medium text-slate-500">
                    Signal
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {Object.entries(snapshot.model_breakdown).map(([model, data]) => (
                  <tr key={model} className="bg-slate-900/30">
                    <td className="px-3 py-2 font-medium text-slate-300">{model}</td>
                    <td className="px-3 py-2 text-right text-slate-300">
                      KES {data.price.toFixed(2)}
                    </td>
                    <td
                      className={`px-3 py-2 text-right font-medium ${
                        data.pct >= 0 ? "text-emerald-400" : "text-red-400"
                      }`}
                    >
                      {data.pct >= 0 ? "+" : ""}
                      {data.pct.toFixed(2)}%
                    </td>
                    <td className="px-3 py-2 text-center">
                      <SignalBadge signal={data.signal as "BUY" | "HOLD" | "SELL"} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {snapshot.model_agreement !== undefined && (
            <p className="mt-1.5 text-xs text-slate-500">
              Model agreement:{" "}
              <span className="font-medium text-slate-400">{snapshot.model_agreement}%</span>
            </p>
          )}
        </div>
      )}

      {/* Accuracy metrics */}
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricChip label="MAPE" value={`${snapshot.metrics.mape.toFixed(1)}%`} />
        <MetricChip label="RMSE" value={snapshot.metrics.rmse.toFixed(3)} />
        <MetricChip label="MAE" value={snapshot.metrics.mae.toFixed(3)} />
        <MetricChip
          label="Directional Acc."
          value={`${snapshot.metrics.directional_accuracy.toFixed(0)}%`}
        />
      </div>
      {(snapshot.recent_mape !== undefined || snapshot.recent_direction_acc !== undefined) && (
        <div className="mt-3 flex gap-4 text-xs text-slate-500">
          {snapshot.recent_mape !== undefined && (
            <span>
              Recent MAPE:{" "}
              <span className="font-medium text-slate-400">
                {snapshot.recent_mape.toFixed(1)}%
              </span>
            </span>
          )}
          {snapshot.recent_direction_acc !== undefined && (
            <span>
              Recent Dir. Acc.:{" "}
              <span className="font-medium text-slate-400">
                {snapshot.recent_direction_acc.toFixed(0)}%
              </span>
            </span>
          )}
        </div>
      )}
      <p className="mt-2 text-xs text-slate-600">VaR (95%): {snapshot.var_95_pct.toFixed(2)}%</p>
    </Card>
  );
};

const TechnicalsSection: FC<{ technicals: TechnicalsDoc }> = ({ technicals }) => {
  const fmt = (v: number | null, suffix = "") =>
    v !== null ? `${v.toFixed(2)}${suffix}` : "N/A";

  return (
    <Card>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Technical Indicators
        </h2>
        <span className="text-xs text-slate-500">
          As of {fmtDate(technicals.date)}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        <MetricChip label="RSI (14)" value={fmt(technicals.rsi_14)} />
        <MetricChip label="SMA 20" value={technicals.sma_20 !== null ? `KES ${fmt(technicals.sma_20)}` : "N/A"} />
        <MetricChip label="SMA 50" value={technicals.sma_50 !== null ? `KES ${fmt(technicals.sma_50)}` : "N/A"} />
        <MetricChip label="SMA 200" value={technicals.sma_200 !== null ? `KES ${fmt(technicals.sma_200)}` : "N/A"} />
        <MetricChip label="EMA 12" value={technicals.ema_12 !== null ? `KES ${fmt(technicals.ema_12)}` : "N/A"} />
        <MetricChip label="EMA 26" value={technicals.ema_26 !== null ? `KES ${fmt(technicals.ema_26)}` : "N/A"} />
        <MetricChip label="Daily Return" value={fmt(technicals.daily_return, "%")} />
        <MetricChip label="Volatility 30d" value={fmt(technicals.volatility_30d, "%")} />
        <MetricChip label="Volume" value={technicals.volume.toLocaleString()} />
        <MetricChip label="Avg Vol 30d" value={technicals.avg_volume_30d.toLocaleString()} />
        {technicals.macd !== null && (
          <MetricChip label="MACD" value={fmt(technicals.macd)} />
        )}
        {technicals.rsi_14 !== null && (
          <MetricChip
            label="RSI Status"
            value={
              technicals.rsi_14 > 70
                ? "Overbought"
                : technicals.rsi_14 < 30
                ? "Oversold"
                : "Neutral"
            }
          />
        )}
      </div>

      {Object.keys(technicals.monthly_heatmap).length > 0 && (
        <div className="mt-6">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
            Monthly Returns
          </h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(technicals.monthly_heatmap)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([month, ret]) => (
                <div
                  key={month}
                  className={`rounded px-2 py-1 text-xs font-medium ${
                    ret >= 0
                      ? "bg-emerald-500/20 text-emerald-400"
                      : "bg-red-500/20 text-red-400"
                  }`}
                >
                  {month}: {ret >= 0 ? "+" : ""}{ret.toFixed(1)}%
                </div>
              ))}
          </div>
        </div>
      )}
    </Card>
  );
};

const Metric: FC<{ label: string; value: React.ReactNode }> = ({ label, value }) => (
  <div>
    <p className="text-xs text-slate-500">{label}</p>
    <div className="mt-1">{value}</div>
  </div>
);

const MetricChip: FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-lg bg-slate-900 p-3">
    <p className="text-xs text-slate-500">{label}</p>
    <p className="mt-0.5 text-sm font-semibold text-slate-200">{value}</p>
  </div>
);
