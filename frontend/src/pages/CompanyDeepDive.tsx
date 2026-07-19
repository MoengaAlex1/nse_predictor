import type { FC } from "react";
import { useParams, Link } from "react-router-dom";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { SparkLine } from "../components/charts/SparkLine";
import { PredictionChart } from "../components/charts/PredictionChart";
import { useCompany, useLatestSnapshot, useLatestTechnicals } from "../hooks/useCompany";
import type { SnapshotDoc, TechnicalsDoc } from "../types";

const fmtDate = (iso: string | null) => {
  if (!iso) return "—";
  return new Date(iso + "T00:00:00").toLocaleDateString("en-KE", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
};

export const CompanyDeepDive: FC = () => {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const { data: company, isLoading, isError } = useCompany(ticker);

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
              <span className="text-3xl">{company.icon}</span>
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
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                Price History ({company.price_history.length} days)
              </h2>
              <span className="text-xs text-slate-500">
                {company.price_history[0]?.date} → {company.price_history[company.price_history.length - 1]?.date}
              </span>
            </div>
            <SparkLine data={company.price_history} color={company.color} />
          </Card>
        ) : company.price_preview.length > 0 ? (
          <Card>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
                30-Day Price Trend
              </h2>
              <span className="text-xs text-slate-500">
                Approximate dates — re-seed for exact trading dates
              </span>
            </div>
            <SparkLine
              data={(() => {
                const ref = company.last_updated
                  ? new Date(company.last_updated + "T00:00:00")
                  : new Date();
                const n = company.price_preview.length;
                // Walk backwards skipping weekends (NSE doesn't trade Sat/Sun)
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
          />
        </Card>
      )}

      {technicals && <TechnicalsSection technicals={technicals} />}
    </div>
  );
};

const SnapshotSection: FC<{ snapshot: SnapshotDoc }> = ({ snapshot }) => (
  <Card>
    <div className="mb-4 flex items-center justify-between">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
        AI Signal
      </h2>
      <span className="text-xs text-slate-500">
        Analysis run: {fmtDate(snapshot.run_date)}
      </span>
    </div>
    <div className="flex flex-wrap gap-6">
      <Metric label="Signal" value={<SignalBadge signal={snapshot.signal} size="lg" />} />
      <Metric
        label="Risk-Adjusted"
        value={<SignalBadge signal={snapshot.risk_adjusted_signal} size="lg" />}
      />
      <Metric
        label="Predicted Price"
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
    <p className="mt-4 text-sm text-slate-400">{snapshot.rationale}</p>
    <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <MetricChip label="MAPE" value={`${snapshot.metrics.mape.toFixed(1)}%`} />
      <MetricChip label="RMSE" value={snapshot.metrics.rmse.toFixed(3)} />
      <MetricChip label="MAE" value={snapshot.metrics.mae.toFixed(3)} />
      <MetricChip
        label="Directional Acc."
        value={`${snapshot.metrics.directional_accuracy.toFixed(0)}%`}
      />
    </div>
    <p className="mt-2 text-xs text-slate-600">VaR (95%): {snapshot.var_95_pct.toFixed(2)}%</p>
  </Card>
);

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
