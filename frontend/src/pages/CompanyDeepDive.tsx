import { useState, useMemo } from "react";
import type { FC } from "react";
import { useParams, Link } from "react-router-dom";
import { fmtDate, fmtMedium, fmtDay, fmtLabel } from "../lib/dateUtils";
import { PageShell } from "../components/layout/PageShell";
import { Card } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { SignalBadge } from "../components/ui/Badge";
import { CompanyLogo } from "../components/ui/CompanyLogo";
import { TradingChart } from "../components/charts/TradingChart";
import { PredictionChart } from "../components/charts/PredictionChart";
import { PriceExplainer } from "../components/company/PriceExplainer";
import { useCompany, useLatestSnapshot, useLatestTechnicals, useCorporateEvents, useFinancials, useMacro, useIntradayDay } from "../hooks/useCompany";
import type { PricePoint, IntradayPoint, SnapshotDoc, TechnicalsDoc, CompanyDoc, CorporateEvent, FinancialsDoc, NSEAnnouncement } from "../types";

// ── Types ─────────────────────────────────────────────────────────────────────
type RangeKey = "1D" | "1M" | "3M" | "6M" | "YTD" | "1Y" | "5Y" | "ALL" | "Custom";
const PRESETS: { label: RangeKey; days: number | null }[] = [
  { label: "1D",     days: 1    },
  { label: "1M",     days: 30   },
  { label: "3M",     days: 90   },
  { label: "6M",     days: 180  },
  { label: "YTD",    days: -1   },
  { label: "1Y",     days: 365  },
  { label: "5Y",     days: 1825 },
  { label: "ALL",    days: null },
  { label: "Custom", days: null },
];

function cleanPriceHistory(points: PricePoint[]): PricePoint[] {
  if (points.length < 5) return points;
  const sorted = points.map((p) => p.price).slice().sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  if (!median || median <= 0) return points;
  return points.filter((p) => {
    const ratio = p.price / median;
    return ratio >= 0.1 && ratio <= 8.0;
  });
}

function filterByRange(data: PricePoint[], range: RangeKey, from: string, to: string): PricePoint[] {
  if (!data.length) return data;
  if (range === "Custom") {
    return data.filter((p) => (!from || p.date >= from) && (!to || p.date <= to));
  }
  if (range === "YTD") {
    const ytdCut = `${new Date().getFullYear()}-01-01`;
    return data.filter((p) => p.date >= ytdCut);
  }
  const days = PRESETS.find((r) => r.label === range)?.days ?? null;
  if (!days) return data;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  return data.filter((p) => p.date >= cutoff.toISOString().slice(0, 10));
}

const priceFmt = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(2)}k` : v.toFixed(2));
const kesFmt = (v: number) =>
  v.toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// ── Metric chip ────────────────────────────────────────────────────────────────
const MetricChip: FC<{ label: string; value: string; accent?: string }> = ({
  label, value, accent,
}) => (
  <div className="rounded-lg border border-seam bg-raised/60 p-3">
    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</p>
    <p className={`mt-0.5 font-mono text-sm font-semibold ${accent ?? "text-ink"}`}>{value}</p>
  </div>
);

// ── Range button ───────────────────────────────────────────────────────────────
const RangeBtn: FC<{ label: RangeKey; active: boolean; onClick: () => void }> = ({
  label, active, onClick,
}) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded px-2.5 py-1 text-xs font-semibold transition-colors ${
      active ? "bg-sky-600 text-white" : "text-muted hover:bg-rim hover:text-sub"
    }`}
  >
    {label}
  </button>
);

// ── RSI visual gauge ───────────────────────────────────────────────────────────
const RSIGauge: FC<{ rsi: number }> = ({ rsi }) => {
  const clamped = Math.min(100, Math.max(0, rsi));
  const status =
    rsi > 70 ? { text: "Overbought", color: "#ef4444" }
    : rsi < 30 ? { text: "Oversold",   color: "#22c55e" }
    : { text: "Neutral", color: "#94a3b8" };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted">RSI (14)</span>
        <span className="font-mono text-sm font-bold" style={{ color: status.color }}>
          {rsi.toFixed(1)} · {status.text}
        </span>
      </div>
      <div className="relative h-2.5 overflow-hidden rounded-full bg-raised">
        <div className="absolute left-0 top-0 h-full w-[30%] bg-emerald-500/20 rounded-l-full" />
        <div className="absolute right-0 top-0 h-full w-[30%] bg-red-500/20 rounded-r-full" />
        <div
          className="absolute top-1/2 h-4 w-4 -translate-y-1/2 rounded-full border-2 border-canvas shadow-lg transition-all duration-500"
          style={{ left: `${clamped}%`, transform: "translate(-50%, -50%)", backgroundColor: status.color }}
        />
      </div>
      <div className="flex justify-between text-[10px] font-mono text-hint">
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
      <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
        Monthly Returns
      </p>
      <div className="flex flex-wrap gap-1.5">
        {entries.map(([month, ret]) => {
          month.split("-");
          const mo = new Date(`${month}-01T00:00:00`).toLocaleDateString("en-KE", { month: "short", year: "2-digit" });
          return (
            <div
              key={month}
              className={`flex flex-col items-center rounded px-2 py-1.5 ${color(ret)}`}
              title={`${mo}: ${ret >= 0 ? "+" : ""}${ret.toFixed(2)}%`}
            >
              <span className="font-mono text-[9px] font-medium opacity-70">{mo}</span>
              <span className="font-mono text-xs font-bold">{ret >= 0 ? "+" : ""}{ret.toFixed(1)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── Stats strip (range-aware) ──────────────────────────────────────────────────
const StatsStrip: FC<{
  data: PricePoint[];
  range: RangeKey;
  currentPrice: number | null;
  technicals: TechnicalsDoc | null | undefined;
}> = ({ data, range, currentPrice, technicals }) => {
  const periodStats = useMemo(() => {
    if (!data.length) return null;
    const prices = data.map((p) => p.price);
    return { high: Math.max(...prices), low: Math.min(...prices) };
  }, [data]);

  const periodPos = periodStats && currentPrice && periodStats.high !== periodStats.low
    ? ((currentPrice - periodStats.low) / (periodStats.high - periodStats.low)) * 100
    : null;

  const periodLabel =
    range === "1D"     ? "Today"    :
    range === "ALL"    ? "All-time" :
    range === "YTD"    ? "YTD"      :
    range === "Custom" ? "Period"   : range;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
      {periodStats && (
        <>
          <div className="rounded-lg border border-seam bg-surface p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{periodLabel} High</p>
            <p className="mt-0.5 font-mono text-sm font-bold text-emerald-500">
              KES {priceFmt(periodStats.high)}
            </p>
          </div>
          <div className="rounded-lg border border-seam bg-surface p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{periodLabel} Low</p>
            <p className="mt-0.5 font-mono text-sm font-bold text-red-500">
              KES {priceFmt(periodStats.low)}
            </p>
          </div>
          {periodPos !== null && (
            <div className="col-span-2 rounded-lg border border-seam bg-surface p-3">
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
                {periodLabel} Range · {periodPos.toFixed(0)}% from low
              </p>
              <div className="relative h-1.5 rounded-full bg-raised">
                <div
                  className="absolute left-0 top-0 h-full rounded-full bg-sky-500"
                  style={{ width: `${Math.min(100, periodPos)}%` }}
                />
              </div>
              <div className="mt-1 flex justify-between text-[9px] font-mono text-hint">
                <span>{priceFmt(periodStats.low)}</span>
                <span>{priceFmt(periodStats.high)}</span>
              </div>
            </div>
          )}
        </>
      )}
      {technicals?.avg_volume_30d != null && (
        <div className="rounded-lg border border-seam bg-surface p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Avg Vol 30d</p>
          <p className="mt-0.5 font-mono text-sm font-semibold text-ink">
            {technicals.avg_volume_30d >= 1_000_000
              ? `${(technicals.avg_volume_30d / 1_000_000).toFixed(1)}M`
              : technicals.avg_volume_30d >= 1_000
              ? `${(technicals.avg_volume_30d / 1_000).toFixed(0)}K`
              : technicals.avg_volume_30d.toLocaleString()}
          </p>
        </div>
      )}
      {technicals?.volatility_30d != null && (
        <div className="rounded-lg border border-seam bg-surface p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Volatility 30d</p>
          <p className="mt-0.5 font-mono text-sm font-semibold text-ink">
            {technicals.volatility_30d.toFixed(2)}%
          </p>
        </div>
      )}
    </div>
  );
};

// ── Range performance strip ────────────────────────────────────────────────────
const RangePerformance: FC<{ data: PricePoint[]; range: RangeKey }> = ({ data, range }) => {
  const stats = useMemo(() => {
    if (data.length < 2) return null;
    const startPrice = data[0].price;
    const endPrice   = data[data.length - 1].price;
    const prices     = data.map((p) => p.price);
    const high       = Math.max(...prices);
    const low        = Math.min(...prices);
    const change     = endPrice - startPrice;
    const changePct  = (change / startPrice) * 100;
    return { startPrice, endPrice, high, low, change, changePct, startDate: data[0].date, endDate: data[data.length - 1].date };
  }, [data]);

  if (!stats) return null;

  const isGain      = stats.changePct >= 0;
  const sign        = isGain ? "+" : "";
  const color       = isGain ? "text-emerald-500" : "text-red-500";
  const bgColor     = isGain ? "bg-emerald-500/10 border-emerald-500/20" : "bg-red-500/10 border-red-500/20";
  const rangeLabel  = range === "YTD" ? "Year to Date" : range === "Custom" ? "Custom Range" : `${range} Performance`;

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted">{rangeLabel}</p>
      <div className="flex flex-wrap gap-4">
        {/* Big return number */}
        <div className={`flex min-w-[160px] flex-1 flex-col justify-center rounded-lg border p-4 ${bgColor}`}>
          <span className={`font-mono text-4xl font-black leading-none ${color}`}>
            {sign}{stats.changePct.toFixed(2)}%
          </span>
          <span className={`mt-1 font-mono text-sm font-semibold ${color}`}>
            {sign}KES {kesFmt(Math.abs(stats.change))} per share
          </span>
          <span className="mt-0.5 text-[10px] text-muted">
            {isGain ? "Gain" : "Loss"} over {data.length} trading days
          </span>
        </div>
        {/* Stat grid */}
        <div className="grid flex-1 grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg border border-seam bg-raised/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">Start Price</p>
            <p className="mt-0.5 font-mono text-sm font-bold text-ink">KES {kesFmt(stats.startPrice)}</p>
            <p className="text-[10px] font-mono text-hint">{stats.startDate}</p>
          </div>
          <div className="rounded-lg border border-seam bg-raised/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">End Price</p>
            <p className="mt-0.5 font-mono text-sm font-bold text-ink">KES {kesFmt(stats.endPrice)}</p>
            <p className="text-[10px] font-mono text-hint">{stats.endDate}</p>
          </div>
          <div className="rounded-lg border border-seam bg-raised/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">Period High</p>
            <p className="mt-0.5 font-mono text-sm font-bold text-emerald-500">KES {kesFmt(stats.high)}</p>
          </div>
          <div className="rounded-lg border border-seam bg-raised/60 p-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">Period Low</p>
            <p className="mt-0.5 font-mono text-sm font-bold text-red-500">KES {kesFmt(stats.low)}</p>
          </div>
        </div>
      </div>
    </div>
  );
};

// ── Investment calculator ──────────────────────────────────────────────────────
const InvestmentCalculator: FC<{ data: PricePoint[]; range: RangeKey }> = ({ data, range }) => {
  const [shares, setShares] = useState("100");

  const calc = useMemo(() => {
    if (data.length < 2) return null;
    const qty        = Math.max(0, parseFloat(shares) || 0);
    const entryPrice = data[0].price;
    const exitPrice  = data[data.length - 1].price;
    const invested   = qty * entryPrice;
    const nowValue   = qty * exitPrice;
    const pnl        = nowValue - invested;
    const returnPct  = invested > 0 ? (pnl / invested) * 100 : 0;
    return { qty, entryPrice, exitPrice, invested, nowValue, pnl, returnPct };
  }, [data, shares]);

  if (!calc) return null;

  const isGain     = calc.pnl >= 0;
  const color      = isGain ? "text-emerald-500" : "text-red-500";
  const pnlBorder  = isGain ? "border-emerald-500/30 bg-emerald-500/10" : "border-red-500/30 bg-red-500/10";
  const rangeLabel = range === "YTD" ? "YTD" : range === "Custom" ? "selected" : range;

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted">Investment Calculator</p>
          <p className="mt-0.5 text-[11px] text-hint">
            If you had bought {calc.qty > 0 ? calc.qty.toLocaleString() : "X"} shares at the start of the {rangeLabel} period
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[10px] font-semibold uppercase tracking-wider text-hint" htmlFor="calc-shares">
            Shares
          </label>
          <input
            id="calc-shares"
            type="number"
            min="1"
            step="1"
            value={shares}
            onChange={(e) => setShares(e.target.value)}
            className="w-28 rounded-lg border border-rim bg-raised px-3 py-1.5 font-mono text-sm font-bold text-ink focus:border-accent focus:outline-none"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-seam bg-raised/60 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">Entry Price</p>
          <p className="mt-0.5 font-mono text-sm font-bold text-ink">KES {kesFmt(calc.entryPrice)}</p>
          <p className="text-[10px] text-hint">{data[0].date}</p>
        </div>
        <div className="rounded-lg border border-seam bg-raised/60 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">Total Invested</p>
          <p className="mt-0.5 font-mono text-sm font-bold text-ink">
            {calc.invested > 0 ? `KES ${kesFmt(calc.invested)}` : "—"}
          </p>
        </div>
        <div className="rounded-lg border border-seam bg-raised/60 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">Value Today</p>
          <p className="mt-0.5 font-mono text-sm font-bold text-ink">
            {calc.nowValue > 0 ? `KES ${kesFmt(calc.nowValue)}` : "—"}
          </p>
          <p className="text-[10px] font-mono text-hint">@ KES {kesFmt(calc.exitPrice)}</p>
        </div>
        <div className={`rounded-lg border p-3 ${pnlBorder}`}>
          <p className="text-[10px] font-semibold uppercase tracking-wider text-hint">
            {isGain ? "Profit" : "Loss"}
          </p>
          {calc.invested > 0 ? (
            <>
              <p className={`mt-0.5 font-mono text-sm font-bold ${color}`}>
                {isGain ? "+" : "−"}KES {kesFmt(Math.abs(calc.pnl))}
              </p>
              <p className={`font-mono text-xs font-bold ${color}`}>
                {isGain ? "+" : ""}{calc.returnPct.toFixed(2)}%
              </p>
            </>
          ) : (
            <p className="mt-0.5 text-xs text-muted">Enter shares above</p>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Filings timeline ───────────────────────────────────────────────────────────
const FILING_TYPE: Record<string, { label: string; pill: string }> = {
  financial_result: { label: "Results",     pill: "bg-sky-900/50 text-sky-300 border-sky-800/50" },
  dividend:         { label: "Dividend",    pill: "bg-emerald-900/50 text-emerald-300 border-emerald-800/50" },
  agm:              { label: "AGM",         pill: "bg-amber-900/50 text-amber-300 border-amber-800/50" },
  corporate_action: { label: "Corp Action", pill: "bg-violet-900/50 text-violet-300 border-violet-800/50" },
};

const FilingsTimeline: FC<{ financials: FinancialsDoc | undefined }> = ({ financials }) => {
  const [activeTab, setActiveTab] = useState("all");

  const entries = useMemo<NSEAnnouncement[]>(() => {
    const list: NSEAnnouncement[] = [];
    (financials?.announcements ?? []).forEach((a) => list.push(a));
    (financials?.corporate_actions ?? []).forEach((a) => {
      if (a.url && a.title) {
        list.push({
          date: a.date,
          type: (a.type as NSEAnnouncement["type"]) || "corporate_action",
          title: a.title,
          url: a.url,
        });
      }
    });
    (financials?.dividends ?? []).forEach((d) => {
      const dd = d as unknown as { date?: string; url?: string; title?: string; type?: string };
      if (dd.url && dd.title && dd.date) {
        list.push({ date: dd.date, type: "dividend", title: dd.title, url: dd.url });
      }
    });
    return list.sort((a, b) => b.date.localeCompare(a.date));
  }, [financials]);

  const tabs = useMemo(() => {
    const counts: Record<string, number> = { all: entries.length };
    entries.forEach((e) => { counts[e.type] = (counts[e.type] ?? 0) + 1; });
    return counts;
  }, [entries]);

  const filtered = activeTab === "all" ? entries : entries.filter((e) => e.type === activeTab);

  if (!entries.length) return null;

  const tabKeys = ["all", "financial_result", "corporate_action", "agm", "dividend"];

  return (
    <Card className="border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-seam">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-sub">
          NSE Filings &amp; Announcements
        </h2>
        <div className="flex flex-wrap gap-1">
          {tabKeys.filter((k) => (tabs[k] ?? 0) > 0).map((k) => {
            const cfg = FILING_TYPE[k];
            const isActive = activeTab === k;
            return (
              <button
                key={k}
                type="button"
                onClick={() => setActiveTab(k)}
                className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold transition-colors ${
                  isActive
                    ? (cfg?.pill ?? "bg-slate-700/60 text-slate-200 border-slate-600")
                    : "border-rim text-muted hover:border-sub hover:text-sub"
                }`}
              >
                {k === "all" ? "All" : cfg?.label ?? k} · {tabs[k]}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-3 space-y-1.5 max-h-[480px] overflow-y-auto pr-1">
        {filtered.map((entry, i) => {
          const cfg = FILING_TYPE[entry.type];
          return (
            <a
              key={i}
              href={entry.url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-raised/60"
            >
              <span className="shrink-0 font-mono text-[10px] text-hint pt-0.5 w-20">
                {entry.date}
              </span>
              <span
                className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${cfg?.pill ?? "bg-slate-700/60 text-slate-300 border-slate-600"}`}
              >
                {cfg?.label ?? entry.type}
              </span>
              <span className="flex-1 text-xs text-sub group-hover:text-ink leading-snug"
                dangerouslySetInnerHTML={{ __html: entry.title.replace(/&#8211;/g, "–").replace(/&amp;/g, "&").replace(/&#8212;/g, "—") }}
              />
              <span className="shrink-0 text-[10px] text-hint group-hover:text-accent">↗</span>
            </a>
          );
        })}
      </div>
    </Card>
  );
};

// ── Chart section ─────────────────────────────────────────────────────────────
const ChartSection: FC<{
  company: CompanyDoc;
  technicals: TechnicalsDoc | null | undefined;
  range: RangeKey;
  setRange: (r: RangeKey) => void;
  from: string;
  setFrom: (s: string) => void;
  to: string;
  setTo: (s: string) => void;
  visible: PricePoint[];
  announcements: NSEAnnouncement[];
  intradayDate?: string;
  intradayDay: string;
  setIntradayDay: (d: string) => void;
  todayEAT: string;
}> = ({ company, technicals, range, setRange, from, setFrom, to, setTo, visible, announcements, intradayDay, setIntradayDay, todayEAT }) => {
  const [showFib, setShowFib]    = useState(true);
  const [showSMAs, setShowSMAs]  = useState(true);
  const [showEvents, setShowEvents] = useState(true);

  const isIntraday = range === "1D";
  const history = cleanPriceHistory(company.price_history ?? []);
  const dataMin = history[0]?.date ?? "";
  const dataMax = history[history.length - 1]?.date ?? "";

  return (
    <div className="space-y-4">
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <div>
          <span className="text-xs font-semibold uppercase tracking-wider text-muted">
            {isIntraday ? "Intraday" : "Price History"}
          </span>
          {visible.length > 0 && (
            <span className="ml-2 font-mono text-[10px] text-hint">
              {isIntraday
                ? `${intradayDay} · ${visible.length} snapshot${visible.length !== 1 ? "s" : ""}`
                : `${visible[0].date} → ${visible[visible.length - 1].date} · ${visible.length} days`}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setShowFib((s) => !s)}
            className={`rounded border px-2 py-1 text-[10px] font-semibold transition-colors ${
              showFib
                ? "border-amber-500 bg-amber-500/10 text-amber-500"
                : "border-rim text-muted hover:border-sub hover:text-sub"
            }`}
          >
            Fib
          </button>
          <button
            type="button"
            onClick={() => setShowSMAs((s) => !s)}
            className={`rounded border px-2 py-1 text-[10px] font-semibold transition-colors ${
              showSMAs
                ? "border-sky-500 bg-sky-500/10 text-sky-500"
                : "border-rim text-muted hover:border-sub hover:text-sub"
            }`}
          >
            MA
          </button>
          {announcements.length > 0 && (
            <button
              type="button"
              onClick={() => setShowEvents((s) => !s)}
              className={`rounded border px-2 py-1 text-[10px] font-semibold transition-colors ${
                showEvents
                  ? "border-violet-500 bg-violet-500/10 text-violet-400"
                  : "border-rim text-muted hover:border-sub hover:text-sub"
              }`}
              title="Toggle NSE filing markers"
            >
              Events
            </button>
          )}
          <div className="flex gap-0.5 rounded-lg border border-rim bg-raised p-0.5">
            {PRESETS.map((r) => (
              <RangeBtn
                key={r.label}
                label={r.label}
                active={range === r.label}
                onClick={() => setRange(r.label)}
              />
            ))}
          </div>
          {range === "1D" && (
            <div className="flex items-center gap-2">
              <input
                type="date"
                value={intradayDay}
                max={todayEAT}
                onChange={(e) => setIntradayDay(e.target.value)}
                className="rounded border border-rim bg-raised px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none"
              />
              {intradayDay !== todayEAT && (
                <button
                  type="button"
                  onClick={() => setIntradayDay(todayEAT)}
                  className="rounded border border-rim px-2 py-1 text-[10px] font-semibold text-muted hover:border-sub hover:text-sub"
                >
                  Today
                </button>
              )}
            </div>
          )}
          {range === "Custom" && (
            <div className="flex items-center gap-2">
              <input type="date" value={from} min={dataMin} max={to || dataMax}
                onChange={(e) => setFrom(e.target.value)}
                className="rounded border border-rim bg-raised px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none" />
              <span className="text-xs text-hint">→</span>
              <input type="date" value={to} min={from || dataMin} max={dataMax}
                onChange={(e) => setTo(e.target.value)}
                className="rounded border border-rim bg-raised px-2 py-1 text-xs text-ink focus:border-accent focus:outline-none" />
            </div>
          )}
        </div>
      </div>

      {!isIntraday && showEvents && announcements.length > 0 && (
        <div className="flex flex-wrap gap-3 border-b border-seam/50 px-4 py-2">
          {[
            { type: "financial_result", color: "#38bdf8", label: "R · Results" },
            { type: "dividend",         color: "#22c55e", label: "D · Dividend" },
            { type: "agm",              color: "#f59e0b", label: "A · AGM" },
            { type: "corporate_action", color: "#a78bfa", label: "C · Corp Action" },
          ]
            .filter(({ type }) => announcements.some((a) => a.type === type))
            .map(({ color, label }) => (
              <span key={label} className="flex items-center gap-1.5 text-[10px] font-mono">
                <svg width="12" height="12" viewBox="0 0 12 12">
                  <circle cx="6" cy="6" r="5" fill={color} opacity="0.88" />
                </svg>
                <span style={{ color }}>{label}</span>
              </span>
            ))}
        </div>
      )}

      {!isIntraday && showSMAs && (technicals?.sma_20 || technicals?.sma_50 || technicals?.sma_200) && (
        <div className="flex gap-4 border-b border-seam/50 px-4 py-2">
          {technicals?.sma_20 != null && (
            <span className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="inline-block h-0.5 w-5 bg-amber-400 opacity-75" />
              <span className="text-amber-500">SMA20 {priceFmt(technicals.sma_20)}</span>
            </span>
          )}
          {technicals?.sma_50 != null && (
            <span className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="inline-block h-0.5 w-5 bg-sky-400 opacity-75" />
              <span className="text-sky-500">SMA50 {priceFmt(technicals.sma_50)}</span>
            </span>
          )}
          {technicals?.sma_200 != null && (
            <span className="flex items-center gap-1.5 text-[10px] font-mono">
              <span className="inline-block h-0.5 w-5 bg-violet-400 opacity-75" />
              <span className="text-violet-500">SMA200 {priceFmt(technicals.sma_200)}</span>
            </span>
          )}
        </div>
      )}

      <div className="px-1 pt-1 pb-3">
        {visible.length > 1 ? (
          <TradingChart
            data={visible}
            color={company.color}
            showFib={!isIntraday && showFib}
            sma20={!isIntraday && showSMAs ? technicals?.sma_20 : null}
            sma50={!isIntraday && showSMAs ? technicals?.sma_50 : null}
            sma200={!isIntraday && showSMAs ? technicals?.sma_200 : null}
            events={!isIntraday && showEvents ? announcements : undefined}
          />
        ) : (
          <div className="flex h-80 items-center justify-center text-muted">
            <p>
              {isIntraday
                ? intradayDay === todayEAT
                  ? "No intraday snapshots yet for today. Data accumulates on each of the 5 daily runs."
                  : `No intraday data recorded for ${intradayDay}.`
                : "Not enough data for this range."}
            </p>
          </div>
        )}
      </div>
    </div>

    {!isIntraday && visible.length >= 2 && (
      <>
        <RangePerformance data={visible} range={range} />
        <InvestmentCalculator data={visible} range={range} />
      </>
    )}
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
      <div className="flex items-center justify-between px-5 py-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted">
            AI Signal · {fmtDate(snapshot.run_date)}
          </p>
          <p className={`mt-1 text-4xl font-black tracking-tight ${style.text}`}>{sig}</p>
          {snapshot.signal !== sig && (
            <p className="mt-1 text-xs text-muted">
              Raw signal: <span className="font-medium text-sub">{snapshot.signal}</span>
              &ensp;(risk-adjusted)
            </p>
          )}
        </div>
        <div className="text-right">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
            Target · {snapshot.next_trading_day}
          </p>
          <p className="mt-1 font-mono text-2xl font-bold text-ink">
            KES {snapshot.predicted_price_KES.toFixed(2)}
          </p>
          <p className={`font-mono text-lg font-bold ${snapshot.predicted_change_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {snapshot.predicted_change_pct >= 0 ? "+" : ""}
            {snapshot.predicted_change_pct.toFixed(2)}%
          </p>
        </div>
      </div>

      {snapshot.confidence_score != null && (
        <div className="border-t border-seam/60 px-5 py-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
              Model Confidence
            </span>
            <span className={`font-mono text-xs font-bold ${style.text}`}>{conf}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-raised">
            <div className={`h-full rounded-full transition-all ${confColor}`} style={{ width: `${conf}%` }} />
          </div>
        </div>
      )}

      {snapshot.signal_reasons?.length ? (
        <div className="border-t border-seam/60 px-5 py-4">
          <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Why this signal
          </p>
          <ul className="space-y-1.5">
            {snapshot.signal_reasons.map((r, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-sub">
                <span className={`mt-0.5 shrink-0 font-bold ${style.text}`}>›</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {snapshot.signal_implications && (
        <div className="border-t border-seam/60 px-5 py-4">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
            What this means for you
          </p>
          <p className="text-sm leading-relaxed text-sub">{snapshot.signal_implications}</p>
        </div>
      )}

      {snapshot.rationale && (
        <div className="border-t border-seam/60 px-5 py-3">
          <p className="text-sm text-sub">{snapshot.rationale}</p>
        </div>
      )}

      {snapshot.model_breakdown && Object.keys(snapshot.model_breakdown).length > 0 && (
        <div className="border-t border-seam/60 px-5 py-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Model Breakdown
            {snapshot.model_agreement != null && (
              <span className="ml-2 text-sub">{snapshot.model_agreement}% agreement</span>
            )}
          </p>
          <div className="overflow-hidden rounded-lg border border-seam">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-raised/60">
                  <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-muted">Model</th>
                  <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Price</th>
                  <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-muted">Change</th>
                  <th className="px-3 py-2 text-center text-[10px] font-semibold uppercase tracking-wider text-muted">Signal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-seam/50">
                {Object.entries(snapshot.model_breakdown).map(([model, d]) => (
                  <tr key={model} className="hover:bg-raised/30 transition-colors">
                    <td className="px-3 py-2.5 font-medium text-sub">{model}</td>
                    <td className="px-3 py-2.5 text-right font-mono text-sub">KES {d.price.toFixed(2)}</td>
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

      <div className="border-t border-seam/60 px-5 py-4">
        <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
          Accuracy Metrics
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricChip label="MAPE" value={`${snapshot.metrics.mape.toFixed(1)}%`} />
          <MetricChip label="RMSE" value={snapshot.metrics.rmse.toFixed(3)} />
          <MetricChip label="MAE"  value={snapshot.metrics.mae.toFixed(3)} />
          <MetricChip label="Dir. Accuracy" value={`${snapshot.metrics.directional_accuracy.toFixed(0)}%`} />
        </div>
        {(snapshot.recent_mape != null || snapshot.recent_direction_acc != null) && (
          <div className="mt-2 flex gap-4 text-xs text-hint">
            {snapshot.recent_mape != null && (
              <span>Recent MAPE: <span className="font-mono font-medium text-muted">{snapshot.recent_mape.toFixed(1)}%</span></span>
            )}
            {snapshot.recent_direction_acc != null && (
              <span>Recent Dir: <span className="font-mono font-medium text-muted">{snapshot.recent_direction_acc.toFixed(0)}%</span></span>
            )}
          </div>
        )}
        <p className="mt-1 font-mono text-[10px] text-hint">
          VaR (95%): {snapshot.var_95_pct.toFixed(2)}%
        </p>
      </div>
    </div>
  );
};

// ── Technicals card ────────────────────────────────────────────────────────────
const TechnicalsCard: FC<{ technicals: TechnicalsDoc }> = ({ technicals }) => {
  const fmt = (v: number | null, suffix = "") => (v !== null ? `${v.toFixed(2)}${suffix}` : "N/A");

  const maRows = [
    { label: "SMA 20",  value: technicals.sma_20,  color: "#f59e0b" },
    { label: "SMA 50",  value: technicals.sma_50,  color: "#38bdf8" },
    { label: "SMA 200", value: technicals.sma_200, color: "#a78bfa" },
    { label: "EMA 12",  value: technicals.ema_12,  color: "#34d399" },
    { label: "EMA 26",  value: technicals.ema_26,  color: "#fb923c" },
  ].filter((r) => r.value !== null);

  return (
    <Card className="space-y-6 border-rim bg-surface">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-sub">
          Technical Indicators
        </h2>
        <span className="font-mono text-xs text-muted">as of {fmtMedium(technicals.date)}</span>
      </div>

      {technicals.rsi_14 !== null && <RSIGauge rsi={technicals.rsi_14} />}

      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        <MetricChip label="Daily Return"   value={fmt(technicals.daily_return, "%")}
          accent={technicals.daily_return !== null ? (technicals.daily_return >= 0 ? "text-emerald-500" : "text-red-500") : undefined} />
        <MetricChip label="Volatility 30d" value={fmt(technicals.volatility_30d, "%")} />
        <MetricChip label="Volume Today"   value={technicals.volume.toLocaleString()} />
        <MetricChip label="Avg Vol 30d"    value={technicals.avg_volume_30d.toLocaleString()} />
        {technicals.macd !== null && (
          <MetricChip label="MACD" value={fmt(technicals.macd)}
            accent={technicals.macd >= 0 ? "text-emerald-500" : "text-red-500"} />
        )}
        {technicals.macd_hist !== null && (
          <MetricChip label="MACD Hist" value={fmt(technicals.macd_hist)}
            accent={technicals.macd_hist >= 0 ? "text-emerald-500" : "text-red-500"} />
        )}
        {technicals.bb_upper !== null && <MetricChip label="BB Upper" value={`KES ${fmt(technicals.bb_upper)}`} />}
        {technicals.bb_lower !== null && <MetricChip label="BB Lower" value={`KES ${fmt(technicals.bb_lower)}`} />}
      </div>

      {maRows.length > 0 && (
        <div>
          <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Moving Averages
          </p>
          <div className="overflow-hidden rounded-lg border border-seam">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-raised/60">
                  <th className="px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wider text-hint">Period</th>
                  <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-hint">Value</th>
                  <th className="px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wider text-hint">vs Price</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-seam/50">
                {maRows.map((row) => (
                  <tr key={row.label} className="hover:bg-raised/30 transition-colors">
                    <td className="px-3 py-2.5 flex items-center gap-2">
                      <span className="inline-block h-0.5 w-4 rounded" style={{ backgroundColor: row.color }} />
                      <span className="font-semibold text-sub">{row.label}</span>
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono font-semibold text-ink">
                      KES {row.value!.toFixed(2)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <span className="text-hint">—</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {Object.keys(technicals.monthly_heatmap).length > 0 && (
        <MonthlyHeatmap heatmap={technicals.monthly_heatmap} />
      )}
    </Card>
  );
};

// ── Gated content ──────────────────────────────────────────────────────────────
const GatedContent: FC<{
  snapshot: SnapshotDoc | null | undefined;
  snapLoading: boolean;
  technicals: TechnicalsDoc | null | undefined;
  techLoading: boolean;
}> = ({ snapshot, snapLoading, techLoading, technicals }) => {
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
        <Card className="border-rim bg-surface/50">
          <p className="text-sm text-sub">No prediction data yet. Pipeline runs daily at 18:00 EAT.</p>
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

      {technicals && <TechnicalsCard technicals={technicals} />}
    </div>
  );
};

// ── Data quality banner ────────────────────────────────────────────────────────
const DataQualityBanner: FC<{ history: PricePoint[] }> = ({ history }) => {
  const lastDate = history.length > 0 ? history[history.length - 1].date : null;
  const daysSinceLast = lastDate
    ? Math.floor((Date.now() - new Date(lastDate + "T00:00:00").getTime()) / (1000 * 60 * 60 * 24))
    : null;

  const hasNoData  = history.length === 0;
  const hasDataGap = !hasNoData && daysSinceLast !== null && daysSinceLast > 60;

  // Detect the first internal gap > 90 days within the last 3 years.
  // This catches cases where the most-recent data point is today but there is
  // a large hole in the middle of the history (e.g. NSE/SCOM Oct 2025–Jul 2026).
  const internalGap = useMemo(() => {
    if (hasNoData || hasDataGap || history.length < 2) return null;
    const cutoffMs = Date.now() - 3 * 365 * 24 * 60 * 60 * 1000;
    const recent = history.filter(
      p => new Date(p.date + "T00:00:00").getTime() >= cutoffMs
    );
    for (let i = 1; i < recent.length; i++) {
      const prevMs = new Date(recent[i - 1].date + "T00:00:00").getTime();
      const currMs = new Date(recent[i].date + "T00:00:00").getTime();
      const gapDays = (currMs - prevMs) / (1000 * 60 * 60 * 24);
      if (gapDays > 90) {
        return { from: recent[i - 1].date, to: recent[i].date, days: Math.round(gapDays) };
      }
    }
    return null;
  }, [history, hasNoData, hasDataGap]);

  const hasLimitedData = !hasNoData && !hasDataGap && !internalGap && history.length < 30;

  if (!hasNoData && !hasDataGap && !internalGap && !hasLimitedData) return null;

  const message = hasNoData
    ? "No price history is available for this security. It may be newly listed or data is pending."
    : hasDataGap
    ? `Price data may be incomplete. Last recorded price: ${lastDate} (${daysSinceLast} days ago). NSE data sources may have a gap for this security.`
    : internalGap
    ? `Price history has a data gap of ~${Math.round(internalGap.days / 30)} months (${internalGap.from} → ${internalGap.to}). NSE data for this period is unavailable from our sources.`
    : `Limited trading history available (${history.length} trading ${history.length === 1 ? "day" : "days"} recorded). This security may be newly listed or thinly traded.`;

  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-700/40 bg-amber-950/25 px-4 py-3">
      <span className="mt-0.5 shrink-0 text-amber-400">⚠</span>
      <p className="text-xs leading-relaxed text-amber-300/80">{message}</p>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────
export const CompanyDeepDive: FC = () => {
  const { ticker = "" } = useParams<{ ticker: string }>();
  const { data: company, isLoading, isError } = useCompany(ticker);
  const { data: snapshot, isLoading: snapLoading } = useLatestSnapshot(ticker);
  const { data: technicals, isLoading: techLoading } = useLatestTechnicals(ticker);
  const { data: events = [] } = useCorporateEvents(ticker);
  const { data: financials } = useFinancials(ticker);
  const { data: macro } = useMacro();

  // Today's date in EAT (UTC+3) — must be defined before state that depends on it
  const todayEAT = new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString().slice(0, 10);

  // Range state lives here so both StatsStrip and ChartSection share it
  const [range, setRange]             = useState<RangeKey>("3M");
  const [from, setFrom]               = useState("");
  const [to, setTo]                   = useState("");
  const [intradayDay, setIntradayDay] = useState(todayEAT);

  const { data: historicalIntraday } = useIntradayDay(
    ticker,
    intradayDay,
    range === "1D" && intradayDay !== todayEAT,
  );

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
          <Link to="/companies" className="mt-2 block text-sm text-accent hover:underline">
            ← Back to companies
          </Link>
        </Card>
      </PageShell>
    );
  }

  const change  = company.change_pct_today;
  const history = cleanPriceHistory(company.price_history ?? []);

  const intradaySource: IntradayPoint[] | undefined =
    range === "1D"
      ? intradayDay === todayEAT
        ? company.intraday_today
        : (historicalIntraday ?? undefined)
      : undefined;

  const intradayPoints: PricePoint[] | undefined =
    intradaySource && intradaySource.length > 0
      ? intradaySource.map((p) => ({ date: p.time, price: p.price }))
      : undefined;

  const visible = intradayPoints ?? filterByRange(history, range, from, to);

  const rangeLabel =
    range === "1D"     ? "Intraday"     :
    range === "1M"     ? "1 Month"      :
    range === "3M"     ? "3 Months"     :
    range === "6M"     ? "6 Months"     :
    range === "YTD"    ? "Year to Date" :
    range === "1Y"     ? "1 Year"       :
    range === "5Y"     ? "5 Years"      :
    range === "ALL"    ? "All Time"     :
    "Custom Period";

  return (
    <PageShell>
      <div className="space-y-4">
        {/* ── Trading terminal header ────────────────────────────────────── */}
        <div className="overflow-hidden rounded-xl border border-rim bg-surface shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4 px-5 py-5">
            <div className="flex items-start gap-4">
              <CompanyLogo
                id={ticker}
                short={company.short}
                color={company.color}
                icon={company.icon}
                size="xl"
              />
              <div>
                <h1 className="text-2xl font-bold leading-tight text-ink">
                  {company.name}
                </h1>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <span
                    className="rounded border px-2 py-0.5 font-mono text-xs font-bold tracking-wider"
                    style={{ borderColor: `${company.color}55`, color: company.color, backgroundColor: `${company.color}15` }}
                  >
                    {company.ticker}
                  </span>
                  <span className="text-xs text-muted">{company.sector}</span>
                </div>
                {company.price_date && (
                  <p className="mt-1.5 text-[10px] text-hint">
                    Price as of <span className="font-semibold text-muted">{fmtLabel(company.price_date)}</span>
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-start gap-5">
              <div className="text-right">
                {company.current_price !== null ? (
                  <>
                    <p className="font-mono text-4xl font-black tracking-tight text-ink">
                      KES {company.current_price.toFixed(2)}
                    </p>
                    {change !== null && (
                      <div
                        className={`mt-1 inline-flex items-center gap-1 rounded px-2 py-0.5 font-mono text-sm font-bold ${
                          change >= 0
                            ? "bg-emerald-500/10 text-emerald-600 dark:bg-emerald-900/50 dark:text-emerald-400"
                            : "bg-red-500/10 text-red-600 dark:bg-red-900/50 dark:text-red-400"
                        }`}
                      >
                        {change >= 0 ? "▲" : "▼"}{" "}
                        {change >= 0 ? "+" : ""}{change.toFixed(2)}% on {company.price_date ? fmtDay(company.price_date) : "prev close"}
                      </div>
                    )}
                    {company.price_date && (
                      <p className="mt-1 text-right text-[10px] text-hint">
                        Closing price · {fmtLabel(company.price_date)}
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-sm text-muted">Price unavailable</p>
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

        {/* ── Stats strip — reacts to selected range ────────────────────── */}
        <StatsStrip
          data={visible.length > 0 ? visible : history}
          range={range}
          currentPrice={company.current_price}
          technicals={technicals}
        />

        {/* ── Data quality banner (shows for gaps / limited / no history) ── */}
        <DataQualityBanner history={history} />

        {/* ── Trading chart ─────────────────────────────────────────────── */}
        {(history.length > 1 || range === "1D") && (
          <ChartSection
            company={company}
            technicals={technicals}
            range={range}
            setRange={setRange}
            from={from}
            setFrom={setFrom}
            to={to}
            setTo={setTo}
            visible={visible}
            announcements={financials?.announcements ?? []}
            intradayDate={company.intraday_date}
            intradayDay={intradayDay}
            setIntradayDay={setIntradayDay}
            todayEAT={todayEAT}
          />
        )}

        {/* ── AI price explainer ────────────────────────────────────────── */}
        {range !== "1D" && visible.length >= 2 && (
          <PriceExplainer
            company={company}
            visible={visible}
            technicals={technicals}
            rangeLabel={rangeLabel}
            events={events as CorporateEvent[]}
            financials={financials}
            macro={macro}
          />
        )}

        {/* ── NSE filings timeline ──────────────────────────────────────── */}
        <FilingsTimeline financials={financials ?? undefined} />

        {/* ── AI signal + technicals ────────────────────────────────────── */}
        <GatedContent
          snapshot={snapshot}
          snapLoading={snapLoading}
          technicals={technicals}
          techLoading={techLoading}
        />
      </div>
    </PageShell>
  );
};
