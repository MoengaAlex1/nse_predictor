import { useState, useMemo } from "react";
import type { FC } from "react";
import { useParams, Link } from "react-router-dom";
import { fmtDate, fmtMedium } from "../lib/dateUtils";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { CompanyLogo } from "../components/ui/CompanyLogo";
import { TradingChart } from "../components/charts/TradingChart";
import { PredictionChart } from "../components/charts/PredictionChart";
import { useCompany, useLatestSnapshot, useLatestTechnicals } from "../hooks/useCompany";
import type { PricePoint, SnapshotDoc, TechnicalsDoc, CompanyDoc } from "../types";

// ── Types ─────────────────────────────────────────────────────────────────────
type RangeKey = "1M" | "3M" | "6M" | "1Y" | "ALL" | "Custom";
const PRESETS: { label: RangeKey; days: number | null }[] = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
  { label: "ALL", days: null },
  { label: "Custom", days: null },
];

function filterByRange(data: PricePoint[], range: RangeKey, from: string, to: string): PricePoint[] {
  if (!data.length) return data;
  if (range === "Custom") {
    return data.filter((p) => (!from || p.date >= from) && (!to || p.date <= to));
  }
  const days = PRESETS.find((r) => r.label === range)?.days ?? null;
  if (!days) return data;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  return data.filter((p) => p.date >= cutoff.toISOString().slice(0, 10));
}

// ── Tiny helpers ───────────────────────────────────────────────────────────────
const priceFmt = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(2)}k` : v.toFixed(2));

const MetricChip: FC<{ label: string; value: string; accent?: string }> = ({
  label, value, accent,
}) => (
  <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</p>
    <p className={`mt-0.5 font-mono text-sm font-semibold ${accent ?? "text-slate-200"}`}>{value}</p>
  </div>
);

const RangeBtn: FC<{ label: RangeKey; active: boolean; onClick: () => void }> = ({
  label, active, onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
      active ? "bg-sky-600 text-white" : "text-slate-400 hover:bg-slate-700 hover:text-slate-200"
    }`}
  >
    {label}
  </button>
);

// ── RSI visual gauge ──────────────────────────────────────────────────────────
const RSIGauge: FC<{ rsi: number }> = ({ rsi }) => {
  const clamped = Math.min(100, Math.max(0, rsi));
  const status =
    rsi > 70 ? { text: "Overbought", color: "#ef4444" }
    : rsi < 30 ? { text: "Oversold",   color: "#22c55e" }
    : { text: "Neutral", color: "#94a3b8" };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">RSI (14)</span>
        <span className="font-mono text-sm font-bold" style={{ color: status.color }}>
          {rsi.toFixed(1)} · {status.text}
        </span>
      </div>
      <div className="relative h-2.5 overflow-hidden rounded-full bg-slate-800">
        {/* Zone backgrounds */}
        <div className="absolute left-0 top-0 h-full w-[30%] bg-emerald-500/20 rounded-l-full" />
        <div className="absolute right-0 top-0 h-full w-[30%] bg-red-500/20 rounded-r-full" />
        {/* Needle */}
        <div
          className="absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-slate-900 shadow-lg transition-all duration-500"
          style={{ left: `${clamped}%`, transform: "translate(-50%, -50%)", backgroundColor: status.color }}
        />
      </div>
      <div className="flex justify-between text-[10px] font-mono text-slate-600">
        <span>0</span>
        <span className="text-emerald-600">30</span>
        <span className="text-red-600">70</span>
        <span>100</span>
      </div>
    </div>
  );
};

// ── Monthly heatmap ────────────────────────────────────────────────────────────
const MonthlyHeatmap: FC<{ heatmap: Record<string, number> }> = ({ heatmap }) => {
  const entries = Object.entries(heatmap).sort(([a], [b]) => a.localeCompare(b)).slice(-24);
  if (!entries.length) return null;

  const color = (ret: number) => {
    if (ret >= 5)  return "bg-emerald-600/80 text-emerald-100";
    if (ret >= 2)  return "bg-emerald-700/50 text-emerald-300";
    if (ret >= 0)  return "bg-emerald-900/40 text-emerald-400";
    if (ret >= -2) return "bg-red-900/40 text-red-400";
    if (ret >= -5) return "bg-red-700/50 text-red-300";
    return "bg-red-600/80 text-red-100";
  };

  return (
    <div>
      <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        Monthly Returns
      </p>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(([month, ret]) => {
          const [, m] = month.split("-");
          const mo = new Date(`${month}-01T00:00:00`).toLocaleDateString("en-KE", { month: "short", year: "2-digit" });
          return (
            <div key={month} className={`flex flex-col items-center rounded px-2 py-1.5 ${color(ret)}`} title={`${mo}: ${ret >= 0 ? "+" : ""}${ret.toFixed(2)}%`}>
              <span className="font-mono text-[9px] font-medium opacity-70">{mo}</span>
              <span className="font-mono text-xs font-bold">{ret >= 0 ? "+" : ""}{ret.toFixed(1)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── 52-week stats strip ────────────────────────────────────────────────────────
const StatsStrip: FC<{
  company: CompanyDoc;
  technicals: TechnicalsDoc | null | undefined;
}> = ({ company, technicals }) => {
  const stats52w = useMemo(() => {
    if (!company.price_history?.length) return null;
    const cutoff = new Date();
    cutoff.setFullYear(cutoff.getFullYear() - 1);
    const cut = cutoff.toISOString().slice(0, 10);
    const year = company.price_history.filter((p) => p.date >= cut);
    const prices = year.map((p) => p.price);
    if (!prices.length) return null;
    return { high: Math.max(...prices), low: Math.min(...prices) };
  }, [company.price_history]);

  const current = company.current_price;
  const range52 = stats52w && current
    ? ((current - stats52w.low) / (stats52w.high - stats52w.low)) * 100
    : null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
      {stats52w && (
        <>
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">52W High</p>
            <p className="mt-0.5 font-mono text-sm font-bold text-emerald-400">
              KES {priceFmt(stats52w.high)}
            </p>
          </div>
          <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">52W Low</p>
            <p className="mt-0.5 font-mono text-sm font-bold text-red-400">
              KES {priceFmt(stats52w.low)}
            </p>
          </div>
          {range52 !== null && (
            <div className="col-span-2 rounded-lg border border-slate-800 bg-slate-900/50 p-3">
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                52W Range · {range52.toFixed(0)}% from low
              </p>
              <div className="relative h-1.5 rounded-full bg-slate-800">
                <div
                  className="absolute left-0 top-0 h-full rounded-full bg-sky-500"
                  style={{ width: `${Math.min(100, range52)}%` }}
                />
              </div>
              <div className="mt-1 flex justify-between text-[9px] font-mono text-slate-600">
                <span>{priceFmt(stats52w.low)}</span>
                <span>{priceFmt(stats52w.high)}</span>
              </div>
            </div>
          )}
        </>
      )}
      {technicals?.avg_volume_30d != null && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Avg Vol 30d</p>
          <p className="mt-0.5 font-mono text-sm font-semibold text-slate-200">
            {technicals.avg_volume_30d >= 1_000_000
              ? `${(technicals.avg_volume_30d / 1_000_000).toFixed(1)}M`
              : technicals.avg_volume_30d >= 1_000
              ? `${(technicals.avg_volume_30d / 1_000).toFixed(0)}K`
              : technicals.avg_volume_30d.toLocaleString()}
          </p>
        </div>
      )}
      {technicals?.volatility_30d != null && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Volatility 30d</p>
          <p className="mt-0.5 font-mono text-sm font-semibold text-slate-200">
            {technicals.volatility_30d.toFixed(2)}%
          </p>
        </div>
      )}
    </div>
  );
};

// ── Chart section ─────────────────────────────────────────────────────────────
const ChartSection: FC<{
  company: CompanyDoc;
  technicals: TechnicalsDoc | null | undefined;
}> = ({ company, technicals }) => {
  const [range, setRange] = useState<RangeKey>("3M");
  const [from, setFrom] = useState("");
  const [to, setTo]     = useState("");
  const [showFib, setShowFib]   = useState(true);
  const [showSMAs, setShowSMAs] = useState(true);

  const history = company.price_history ?? [];
  const visible = filterByRange(history, range, from, to);
  const dataMin = history[0]?.date ?? "";
  const dataMax = history[history.length - 1]?.date ?? "";

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-[#0d1117]">
      {/* Chart header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            Price History
          </span>
          {visible.length > 0 && (
            <span className="ml-2 font-mono text-[10px] text-slate-600">
              {visible[0].date} → {visible[visible.length - 1].date}
              {" · "}{visible.length} days
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* Overlay toggles */}
          <button
            type="button"
            onClick={() => setShowFib((s) => !s)}
            className={`rounded border px-2 py-1 text-[10px] font-semibold transition-colors ${
              showFib
                ? "border-amber-600 bg-amber-900/30 text-amber-400"
                : "border-slate-700 text-slate-500 hover:border-slate-600 hover:text-slate-400"
            }`}
          >
            Fib
          </button>
          <button
            type="button"
            onClick={() => setShowSMAs((s) => !s)}
            className={`rounded border px-2 py-1 text-[10px] font-semibold transition-colors ${
              showSMAs
                ? "border-sky-700 bg-sky-900/30 text-sky-400"
                : "border-slate-700 text-slate-500 hover:border-slate-600 hover:text-slate-400"
            }`}
          >
            MA
          </button>
          {/* Range selector */}
          <div className="flex gap-0.5 rounded-lg border border-slate-800 bg-slate-900 p-0.5">
            {PRESETS.map((r) => (
              <RangeBtn
                key={r.label}
                label={r.label}
                active={range === r.label}
                onClick={() => setRange(r.label)}
              />
            ))}
          </div>
          {range === "Custom" && (
            <div className="flex items-center gap-2">
              <input type="date" value={from} min={dataMin} max={to || dataMax}
                onChange={(e) => setFrom(e.target.value)}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none" />
              <span className="text-xs text-slate-600">→</span>
              <input type="date" value={to} min={from || dataMin} max={dataMax}
                onChange={(e) => setTo(e.target.value)}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200 focus:border-sky-500 focus:outline-none" />
            </div>
          )}
        </div>
      </div>

      {/* MA legend */}
      {showSMAs && (technicals?.sma_20 || technicals?.sma_50 || technicals?.sma_200) && (
        <div className="flex gap-4 border-b border-slate-800/50 px-4 py-2">
          {technicals?.sma_20 != null && (
            <span className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="inline-block h-0.5 w-5 bg-amber-400 opacity-75" />
              <span className="text-amber-400">SMA20 {priceFmt(technicals.sma_20)}</span>
            </span>
          )}
          {technicals?.sma_50 != null && (
            <span className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="inline-block h-0.5 w-5 bg-sky-400 opacity-75" />
              <span className="text-sky-400">SMA50 {priceFmt(technicals.sma_50)}</span>
            </span>
          )}
          {technicals?.sma_200 != null && (
            <span className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="inline-block h-0.5 w-5 bg-violet-400 opacity-75" />
              <span className="text-violet-400">SMA200 {priceFmt(technicals.sma_200)}</span>
            </span>
          )}
        </div>
      )}

      {/* Chart */}
      <div className="px-1 pt-1 pb-3">
        {visible.length > 1 ? (
          <TradingChart
            data={visible}
            color={company.color}
            showFib={showFib}
            sma20={showSMAs ? technicals?.sma_20 : null}
            sma50={showSMAs ? technicals?.sma_50 : null}
            sma200={showSMAs ? technicals?.sma_200 : null}
          />
        ) : (
          <div className="flex h-80 items-center justify-center text-slate-600">
            <p>Not enough data for this range.</p>
          </div>
        )}
      </div>
    </div>
  );
};

// ── Signal card ────────────────────────────────────────────────────────────────
const SIGNAL_STYLES = {
  BUY:  { border: "border-emerald-800", bg: "bg-emerald-950/40", text: "text-emerald-400", glow: "#10b981" },
  HOLD: { border: "border-amber-800",   bg: "bg-amber-950/40",   text: "text-amber-400",   glow: "#f59e0b" },
  SELL: { border: "border-red-800",     bg: "bg-red-950/40",     text: "text-red-400",     glow: "#ef4444" },
};

const SnapshotCard: FC<{ snapshot: SnapshotDoc }> = ({ snapshot }) => {
  const sig = snapshot.risk_adjusted_signal;
  const style = SIGNAL_STYLES[sig];
  const conf = snapshot.confidence_score ?? 0;
  const confColor = conf >= 70 ? "bg-emerald-500" : conf >= 45 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className={`overflow-hidden rounded-xl border ${style.border} ${style.bg}`}>
      {/* Banner row */}
      <div className="flex items-center justify-between px-5 py-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            AI Signal · {fmtDate(snapshot.run_date)}
          </p>
          <p className={`mt-1 text-4xl font-black tracking-tight ${style.text}`}>{sig}</p>
          {snapshot.signal !== sig && (
            <p className="mt-1 text-xs text-slate-500">
              Raw signal: <span className="font-medium text-slate-400">{snapshot.signal}</span>
              &ensp;(risk-adjusted)
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Target · {snapshot.next_trading_day}
          </p>
          <p className="mt-1 font-mono text-2xl font-bold text-slate-100">
            KES {snapshot.predicted_price_KES.toFixed(2)}
          </p>
          <p
            className={`font-mono text-lg font-bold ${
              snapshot.predicted_change_pct >= 0 ? "text-emerald-400" : "text-red-400"
            }`}
          >
            {snapshot.predicted_change_pct >= 0 ? "+" : ""}
            {snapshot.predicted_change_pct.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* Confidence bar */}
      {snapshot.confidence_score != null && (
        <div className="border-t border-slate-800/60 px-5 py-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Model Confidence
            </span>
            <span className={`font-mono text-xs font-bold ${style.text}`}>{conf}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
            <div className={`h-full rounded-full transition-all ${confColor}`} style={{ width: `${conf}%` }} />
          </div>
        </div>
      )}

      {/* Signal reasons */}
      {snapshot.signal_reasons?.length ? (
        <div className="border-t border-slate-800/60 px-5 py-4">
          <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Why this signal
          </p>
          <ul className="space-y-1.5">
            {snapshot.signal_reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-slate-300">
                <span className={`mt-0.5 shrink-0 font-bold ${style.text}`}>›</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Implications */}
      {snapshot.signal_implications && (
        <div className="border-t border-slate-800/60 px-5 py-4">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            What this means for you
          </p>
          <p className="text-sm leading-relaxed text-slate-300">{snapshot.signal_implications}</p>
        </div>
      )}

      {/* Rationale */}
      {snapshot.rationale && (
        <div className="border-t border-slate-800/60 px-5 py-3">
          <p className="text-sm text-slate-400">{snapshot.rationale}</p>
        </div>
      )}

      {/* Model breakdown */}
      {snapshot.model_breakdown && Object.keys(snapshot.model_breakdown).length > 0 && (
        <div className="border-t border-slate-800/60 px-5 py-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Model Breakdown
            {snapshot.model_agreement != null && (
              <span className="ml-2 text-slate-400">{snapshot.model_agreement}% agreement</span>
            )}
          </p>
          <div className="overflow-hidden rounded-lg border border-slate-800">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-900/60">
                  <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-500">Model</th>
                  <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-slate-500">Price</th>
                  <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-slate-500">Change</th>
                  <th className="px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-wider text-slate-500">Signal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {Object.entries(snapshot.model_breakdown).map(([model, d]) => (
                  <tr key={model} className="hover:bg-slate-800/30 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-slate-300">{model}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-slate-300">KES {d.price.toFixed(2)}</td>
                    <td className={`px-3 py-2.5 text-right font-mono font-semibold ${d.pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {d.pct >= 0 ? "+" : ""}{d.pct.toFixed(2)}%
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <SignalBadge signal={d.signal as "BUY" | "HOLD" | "SELL"} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Accuracy metrics */}
      <div className="border-t border-slate-800/60 px-5 py-4">
        <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Accuracy Metrics
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricChip label="MAPE" value={`${snapshot.metrics.mape.toFixed(1)}%`} />
          <MetricChip label="RMSE" value={snapshot.metrics.rmse.toFixed(3)} />
          <MetricChip label="MAE" value={snapshot.metrics.mae.toFixed(3)} />
          <MetricChip label="Dir. Accuracy" value={`${snapshot.metrics.directional_accuracy.toFixed(0)}%`} />
        </div>
        {(snapshot.recent_mape != null || snapshot.recent_direction_acc != null) && (
          <div className="mt-2 flex gap-4 text-xs text-slate-600">
            {snapshot.recent_mape != null && (
              <span>Recent MAPE: <span className="font-mono font-medium text-slate-500">{snapshot.recent_mape.toFixed(1)}%</span></span>
            )}
            {snapshot.recent_direction_acc != null && (
              <span>Recent Dir: <span className="font-mono font-medium text-slate-500">{snapshot.recent_direction_acc.toFixed(0)}%</span></span>
            )}
          </div>
        )}
        <p className="mt-1 font-mono text-[10px] text-slate-700">
          VaR (95%): {snapshot.var_95_pct.toFixed(2)}%
        </p>
      </div>
    </div>
  );
};

// ── Technicals card ────────────────────────────────────────────────────────────
const TechnicalsCard: FC<{ technicals: TechnicalsDoc; companyColor: string }> = ({
  technicals, companyColor,
}) => {
  const fmt = (v: number | null, suffix = "") => (v !== null ? `${v.toFixed(2)}${suffix}` : "N/A");

  const maRows = [
    { label: "SMA 20",  value: technicals.sma_20,  color: "#f59e0b" },
    { label: "SMA 50",  value: technicals.sma_50,  color: "#38bdf8" },
    { label: "SMA 200", value: technicals.sma_200, color: "#a78bfa" },
    { label: "EMA 12",  value: technicals.ema_12,  color: "#34d399" },
    { label: "EMA 26",  value: technicals.ema_26,  color: "#fb923c" },
  ].filter((r) => r.value !== null);

  return (
    <Card className="space-y-6 border-slate-800 bg-slate-900/70">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Technical Indicators
        </h2>
        <span className="font-mono text-xs text-slate-600">as of {fmtMedium(technicals.date)}</span>
      </div>

      {/* RSI gauge */}
      {technicals.rsi_14 !== null && <RSIGauge rsi={technicals.rsi_14} />}

      {/* Key metrics grid */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        <MetricChip label="Daily Return"   value={fmt(technicals.daily_return, "%")}
          accent={technicals.daily_return !== null ? (technicals.daily_return >= 0 ? "text-emerald-400" : "text-red-400") : undefined} />
        <MetricChip label="Volatility 30d" value={fmt(technicals.volatility_30d, "%")} />
        <MetricChip label="Volume Today"   value={technicals.volume.toLocaleString()} />
        <MetricChip label="Avg Vol 30d"    value={technicals.avg_volume_30d.toLocaleString()} />
        {technicals.macd !== null && (
          <MetricChip label="MACD" value={fmt(technicals.macd)}
            accent={technicals.macd >= 0 ? "text-emerald-400" : "text-red-400"} />
        )}
        {technicals.macd_hist !== null && (
          <MetricChip label="MACD Hist" value={fmt(technicals.macd_hist)}
            accent={technicals.macd_hist >= 0 ? "text-emerald-400" : "text-red-400"} />
        )}
        {technicals.bb_upper !== null && <MetricChip label="BB Upper" value={`KES ${fmt(technicals.bb_upper)}`} />}
        {technicals.bb_lower !== null && <MetricChip label="BB Lower" value={`KES ${fmt(technicals.bb_lower)}`} />}
      </div>

      {/* Moving averages vs current price */}
      {maRows.length > 0 && (
        <div>
          <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Moving Averages
          </p>
          <div className="overflow-hidden rounded-lg border border-slate-800">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-slate-900/60">
                  <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-slate-600">Period</th>
                  <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-slate-600">Value</th>
                  <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-slate-600">vs Price</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/50">
                {maRows.map((row) => {
                  const diff = row.value != null && technicals ? null : null;
                  return (
                    <tr key={row.label} className="hover:bg-slate-800/30 transition-colors">
                      <td className="px-3 py-2.5 flex items-center gap-2">
                        <span className="inline-block h-0.5 w-4 rounded" style={{ backgroundColor: row.color }} />
                        <span className="font-semibold text-slate-400">{row.label}</span>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono font-semibold text-slate-200">
                        KES {row.value!.toFixed(2)}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {/* placeholder – would need current_price passed in */}
                        <span className="text-slate-600">—</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Monthly heatmap */}
      {Object.keys(technicals.monthly_heatmap).length > 0 && (
        <MonthlyHeatmap heatmap={technicals.monthly_heatmap} />
      )}
    </Card>
  );
};

// ── Gated content (snapshot + prediction + technicals) ─────────────────────────
const GatedContent: FC<{
  snapshot: SnapshotDoc | null | undefined;
  snapLoading: boolean;
  technicals: TechnicalsDoc | null | undefined;
  techLoading: boolean;
  companyColor: string;
}> = ({ snapshot, snapLoading, techLoading, technicals, companyColor }) => {
  if (snapLoading || techLoading) {
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {snapshot ? (
        <SnapshotCard snapshot={snapshot} />
      ) : (
        <Card className="border-slate-800 bg-slate-900/50">
          <p className="text-sm text-slate-400">No prediction data yet. Pipeline runs daily at 18:00 EAT.</p>
        </Card>
      )}

      {snapshot && snapshot.actuals.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-[#0d1117]">
          <div className="border-b border-slate-800 px-4 py-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Actual vs Model · Forecast (30d)
            </h2>
            <p className="mt-0.5 text-[10px] text-slate-600">
              Dashed line = today · Green zone = 30-day forecast
            </p>
          </div>
          <div className="px-1 pb-3 pt-1">
            <PredictionChart
              actuals={snapshot.actuals}
              preds={snapshot.preds}
              forecast={snapshot.forecast}
              runDate={snapshot.run_date}
              forecastDates={snapshot.forecast_dates}
            />
          </div>
        </div>
      )}

      {technicals && (
        <TechnicalsCard technicals={technicals} companyColor={companyColor} />
      )}
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────
export const CompanyDeepDive: FC = () => {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const { data: company, isLoading, isError } = useCompany(ticker);
  const { data: snapshot, isLoading: snapLoading } = useLatestSnapshot(ticker);
  const { data: technicals, isLoading: techLoading } = useLatestTechnicals(ticker);

  if (isLoading) {
    return (
      <PageShell>
        <div className="flex justify-center py-20">
          <Spinner size="lg" />
        </div>
      </PageShell>
    );
  }

  if (isError || !company) {
    return (
      <PageShell>
        <Card className="border-red-900 bg-red-950/20">
          <p className="text-red-400">Company not found.</p>
          <Link to="/companies" className="mt-2 block text-sm text-sky-400 hover:underline">
            ← Back to companies
          </Link>
        </Card>
      </PageShell>
    );
  }

  const change = company.change_pct_today;

  return (
    <PageShell>
      <div className="space-y-4">
        {/* ── Trading terminal header ─────────────────────────────────────── */}
        <div className="overflow-hidden rounded-xl border border-slate-800 bg-[#0d1117]">
          <div className="flex flex-wrap items-start justify-between gap-4 px-5 py-5">
            {/* Left: identity */}
            <div className="flex items-start gap-4">
              <CompanyLogo
                id={ticker}
                short={company.short}
                color={company.color}
                icon={company.icon}
                size="xl"
              />
              <div>
                <h1 className="text-2xl font-bold leading-tight text-slate-100">
                  {company.name}
                </h1>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span
                    className="rounded border px-2 py-0.5 font-mono text-xs font-bold tracking-wider"
                    style={{ borderColor: `${company.color}55`, color: company.color, backgroundColor: `${company.color}15` }}
                  >
                    {company.ticker}
                  </span>
                  <span className="text-xs text-slate-500">{company.sector}</span>
                </div>
                {company.last_updated && (
                  <p className="mt-1.5 text-[10px] text-slate-600">
                    Data as of {fmtMedium(company.last_updated)}
                  </p>
                )}
              </div>
            </div>

            {/* Right: price + signal */}
            <div className="flex items-start gap-5">
              <div className="text-right">
                {company.current_price !== null ? (
                  <>
                    <p className="font-mono text-4xl font-black tracking-tight text-slate-100">
                      KES {company.current_price.toFixed(2)}
                    </p>
                    {change !== null && (
                      <div
                        className={`mt-1 inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-sm font-bold ${
                          change >= 0
                            ? "bg-emerald-900/50 text-emerald-400"
                            : "bg-red-900/50 text-red-400"
                        }`}
                      >
                        {change >= 0 ? "▲" : "▼"}{" "}
                        {change >= 0 ? "+" : ""}{change.toFixed(2)}% today
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-slate-500">Price unavailable</p>
                )}
              </div>
              {company.signal && (
                <div className="pt-1">
                  <SignalBadge signal={company.signal} size="lg" />
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── 52W stats strip ─────────────────────────────────────────────── */}
        <StatsStrip company={company} technicals={technicals} />

        {/* ── Trading chart with Fibonacci ─────────────────────────────────── */}
        {(company.price_history?.length ?? 0) > 1 && (
          <ChartSection company={company} technicals={technicals} />
        )}

        {/* ── AI signal + technicals ──────────────────────────────────────── */}
        <GatedContent
          snapshot={snapshot}
          snapLoading={snapLoading}
          technicals={technicals}
          techLoading={techLoading}
          companyColor={company.color}
        />
      </div>
    </PageShell>
  );
};
