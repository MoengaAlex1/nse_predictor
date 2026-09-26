import { useMemo, useState, useRef, useEffect } from "react";
import type { FC } from "react";
import { Link } from "react-router-dom";
import {
  LineChart, BarChart, Line, Bar, XAxis, YAxis, Tooltip, ReferenceLine,
  ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";
import { useCompany, useIntradayDay } from "../../hooks/useCompany";
import { useCompanies } from "../../hooks/useCompanies";
import { useMarketOverview } from "../../hooks/useMarket";
import { usePrices } from "../../hooks/usePrices";
import { fmtCompact, fmtPct, fmtPrice } from "../../lib/format";

// Human labels for chart tooltip. Keeps raw data keys ("bb_lower", "sma20")
// out of the crosshair hover box — the audit flagged the old tooltip for
// showing them verbatim next to 15-digit floats.
const TOOLTIP_LABELS: Record<string, string> = {
  price:    "Close",
  sma20:    "SMA 20",
  sma50:    "SMA 50",
  sma200:   "SMA 200",
  ema12:    "EMA 12",
  ema26:    "EMA 26",
  vwap:     "VWAP 14",
  bb_upper: "BB Upper",
  bb_mid:   "BB Middle",
  bb_lower: "BB Lower",
};
import type { CompanyDoc, IndexReading } from "../../types";

// ─────────────────────────────────────────────────────────────────────────────
// TradingView-style workstation for a single ticker.
//
// This is a native (non-embedded) implementation of the layout the user
// specified in the 2026-09-21 design brief:
//   - Vertical drawing rail on the left (icons only; drawing is out of
//     scope for this shipment — click yields a "coming soon" tooltip).
//   - Top ribbon: symbol / timeframe / chart type / indicators / alert /
//     replay / undo / redo / sub-header / bid-ask execution boxes.
//   - Main canvas: light dotted grid, orange price line, blue live-price
//     Y-axis badge, sharp green/red volume histogram below.
//   - Right sidebar: utilities strip, indices/stocks/futures watchlist,
//     company deep-dive card, news, key stats.
//
// Colour tokens are hard-coded to match TradingView's light theme in the
// spec. If we later add dark-mode toggling, wrap these in CSS custom
// properties. Layout is width-hungry (min 1200px works; below that the
// right sidebar collapses).
// ─────────────────────────────────────────────────────────────────────────────

const COLORS = {
  bg:      "#F8F9FD",
  panel:   "#FFFFFF",
  text:    "#131722",
  muted:   "#5D6778",
  hint:    "#8A96A8",
  border:  "#E0E3EB",
  grid:    "#EEF0F5",
  accent:  "#2962FF",
  orange:  "#FF6D00",
  // Violet used for the primary price line — matches the TradingView
  // reference on NSEKE-COOP / NSEKE-KEGN screenshots. Distinct from
  // brand orange so users don't confuse the line with the NSE
  // Intelligence logo colour.
  priceLine: "#7C3AED",
  livePrice: "#EC4899",
  buy:     "#26A69A",
  sell:    "#EF5350",
  volUp:   "#26A69A",
  volDown: "#EF5350",
};

const RANGES = [
  { key: "1D",     days: 1     },
  { key: "5D",     days: 5     },
  { key: "1M",     days: 30    },
  { key: "3M",     days: 90    },
  { key: "6M",     days: 180   },
  { key: "YTD",    days: -1    },
  { key: "1Y",     days: 365   },
  { key: "5Y",     days: 1825  },
  { key: "All",    days: null  },
  { key: "Custom", days: null  },
] as const;
type RangeKey = typeof RANGES[number]["key"];

// Format an ISO date (YYYY-MM-DD) for the volume x-axis. The label density
// depends on how much time the visible window covers: narrow windows get
// day + month, multi-year ones drop day and pick up the year so we don't
// end up with "Sep / Sep / Sep" all across the strip.
function formatAxisDate(iso: string, spanDays: number): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  if (spanDays <= 5) {
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  }
  if (spanDays <= 400) {
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  }
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

// Full readable date for tooltips: "Fri, 12 Sep 2026". Falls back to the
// raw ISO if the string can't be parsed (defensive — data always ships
// with valid dates today).
function formatTooltipDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

// Default Custom-range window. Anchored to today (- 3 months) so switching
// to Custom lands on a plausible starting selection the user can tweak.
function defaultCustomRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  start.setMonth(start.getMonth() - 3);
  return {
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  };
}

// Kenya-focused watchlist. Two sections:
//   - NSE INDICES: live values from `market_overview.indices` in Firestore
//     (populated by pipeline/src/analysis/indices.py). NASI / NSE 20 / NSE
//     25 / NSE 10 / NSE BSI. M.CAP is intentionally excluded — it's not a
//     tradable index and its scale (billions of KES) throws off the table.
//   - NSE STOCKS: 8 most-followed tickers on the NSE by market cap /
//     liquidity. Prices come from the `useCompanies` feed which already
//     merges the RTDB `prices_latest` mirror into the CompanyDoc.
//
// The old US-heavy watchlist (SPX / AAPL / GOLD / USOIL from yfinance)
// is retired — the pipeline scraper `fetch_external_watchlist.py` keeps
// running to warm the RTDB in case we want to re-expose it via a
// user-toggleable "Global markets" tab later.

// Ordered set of NSE index keys we surface in the watchlist. Keys match
// pipeline/src/analysis/indices.py's canonical output.
const KENYA_INDEX_KEYS: { key: string; label: string; color: string }[] = [
  { key: "NASI",   label: "NASI",   color: "#3B82F6" },
  { key: "NSE20",  label: "NSE 20", color: "#8B5CF6" },
  { key: "NSE25",  label: "NSE 25", color: "#F59E0B" },
  { key: "NSE10",  label: "NSE 10", color: "#10B981" },
  { key: "NSEBSI", label: "NSE BSI", color: "#6366F1" },
];

// Default NSE watchlist stocks. Picked for liquidity + investor coverage;
// users can override this via the search bar to load any listed ticker.
const KENYA_WATCHLIST_STOCKS: string[] = [
  "SCOM", "EQTY", "KCB", "EABL", "COOP", "ABSA", "BAT", "CTUM",
];

// ─── Chart type + indicator config ──────────────────────────────────────
// Chart types the MainCanvas can render. TradingView has ~20 variants
// (candles/HA/renko/kagi/PnF...) but they need real OHLC data at bar
// resolution — our feed is EOD close-only for most tickers, so we ship
// the three types the data actually supports.
type ChartType = "line" | "area" | "columns";

const CHART_TYPES: { key: ChartType; label: string; icon: string }[] = [
  { key: "line",    label: "Line",    icon: "line-chart" },
  { key: "area",    label: "Area",    icon: "area-chart" },
  { key: "columns", label: "Columns", icon: "bar-chart" },
];

// Indicator overlays. All are computed client-side from the price
// series — no extra RTDB read, no dependency on a stale technicals doc.
type IndicatorKey =
  | "sma20" | "sma50" | "sma200"
  | "ema12" | "ema26"
  | "bb"    // Bollinger Bands (20, 2σ)
  | "vwap"; // 14-day rolling VWAP

const INDICATORS: { key: IndicatorKey; label: string; color: string }[] = [
  { key: "sma20",  label: "SMA 20",           color: "#F59E0B" },
  { key: "sma50",  label: "SMA 50",           color: "#38BDF8" },
  { key: "sma200", label: "SMA 200",          color: "#A78BFA" },
  { key: "ema12",  label: "EMA 12",           color: "#34D399" },
  { key: "ema26",  label: "EMA 26",           color: "#FB923C" },
  { key: "bb",     label: "Bollinger Bands",  color: "#94A3B8" },
  { key: "vwap",   label: "VWAP 14",          color: "#EC4899" },
];

interface ChartPoint {
  date: string;
  price: number;
  volume: number;
  up: boolean;
  // Indicator series — populated by decorateWithIndicators. Any missing
  // value is null so Recharts skips the point instead of drawing a
  // straight line to zero.
  sma20?:    number | null;
  sma50?:    number | null;
  sma200?:   number | null;
  ema12?:    number | null;
  ema26?:    number | null;
  bb_upper?: number | null;
  bb_mid?:   number | null;
  bb_lower?: number | null;
  vwap?:     number | null;
}

function rollingMean(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= window) sum -= values[i - window];
    if (i >= window - 1) out[i] = sum / window;
  }
  return out;
}

function ema(values: number[], window: number): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  const k = 2 / (window + 1);
  let prev: number | null = null;
  for (let i = 0; i < values.length; i++) {
    if (prev == null) {
      if (i === window - 1) {
        // Seed with SMA of the first `window` values, matching the
        // convention `ta` uses in pipeline/src/analysis/technicals.py.
        let s = 0;
        for (let j = 0; j < window; j++) s += values[j];
        prev = s / window;
        out[i] = prev;
      }
    } else {
      prev = values[i] * k + prev * (1 - k);
      out[i] = prev;
    }
  }
  return out;
}

function rollingStd(values: number[], window: number, means: (number | null)[]): (number | null)[] {
  const out: (number | null)[] = new Array(values.length).fill(null);
  for (let i = window - 1; i < values.length; i++) {
    const m = means[i];
    if (m == null) continue;
    let sqsum = 0;
    for (let j = i - window + 1; j <= i; j++) sqsum += (values[j] - m) ** 2;
    out[i] = Math.sqrt(sqsum / window);
  }
  return out;
}

/** Decorate every chart point with the currently-active indicator
 *  series. Runs whenever `indicators` or the underlying data changes;
 *  cheap (~O(n × 5) for 500 points). */
function decorateWithIndicators(
  data: ChartPoint[],
  active: Set<IndicatorKey>,
): ChartPoint[] {
  if (!active.size || data.length === 0) return data;
  const prices = data.map((d) => d.price);
  const volumes = data.map((d) => d.volume);

  const sma20  = active.has("sma20")  || active.has("bb") ? rollingMean(prices, 20) : null;
  const sma50  = active.has("sma50")                       ? rollingMean(prices, 50) : null;
  const sma200 = active.has("sma200")                      ? rollingMean(prices, 200) : null;
  const ema12  = active.has("ema12")                       ? ema(prices, 12) : null;
  const ema26  = active.has("ema26")                       ? ema(prices, 26) : null;
  const bbStd  = active.has("bb") && sma20                 ? rollingStd(prices, 20, sma20) : null;

  // 14-day rolling VWAP — price × volume rolling sum / volume rolling sum.
  let vwap: (number | null)[] | null = null;
  if (active.has("vwap")) {
    vwap = new Array(prices.length).fill(null);
    let pv = 0, vv = 0;
    const win = 14;
    for (let i = 0; i < prices.length; i++) {
      pv += prices[i] * volumes[i];
      vv += volumes[i];
      if (i >= win) {
        pv -= prices[i - win] * volumes[i - win];
        vv -= volumes[i - win];
      }
      if (i >= win - 1 && vv > 0) vwap[i] = pv / vv;
    }
  }

  return data.map((d, i) => ({
    ...d,
    sma20:    sma20  ? sma20[i]  : undefined,
    sma50:    sma50  ? sma50[i]  : undefined,
    sma200:   sma200 ? sma200[i] : undefined,
    ema12:    ema12  ? ema12[i]  : undefined,
    ema26:    ema26  ? ema26[i]  : undefined,
    bb_mid:   active.has("bb") && sma20 ? sma20[i] : undefined,
    bb_upper: active.has("bb") && sma20 && bbStd && sma20[i] != null && bbStd[i] != null
      ? (sma20[i] as number) + 2 * (bbStd[i] as number) : undefined,
    bb_lower: active.has("bb") && sma20 && bbStd && sma20[i] != null && bbStd[i] != null
      ? (sma20[i] as number) - 2 * (bbStd[i] as number) : undefined,
    vwap:     vwap ? vwap[i] : undefined,
  }));
}

// ─── Alerts + history state ─────────────────────────────────────────────

interface PriceAlert {
  id: string;
  threshold: number;
  direction: "above" | "below";
  note?: string;
  created_at: string;
}

// Snapshot of the workstation's user-toggleable state, used by the
// undo/redo history stack. Alerts referenced by ID so we don't inflate
// the history with duplicated alert bodies.
interface WsSnapshot {
  range: RangeKey;
  chartType: ChartType;
  indicators: IndicatorKey[];
  alertIds: string[];
}

interface Props {
  short: string;
}

export const TradingWorkstation: FC<Props> = ({ short }) => {
  const { data: company } = useCompany(short);
  const { data: allCompanies = [] } = useCompanies();

  const chartEnd = new Date().toISOString().slice(0, 10);
  const chartStart = "2008-01-01";
  const { rows, latest } = usePrices(short, chartStart, chartEnd);

  const [range, setRange] = useState<RangeKey>("1Y");
  // Intraday for the 1D range. Prefer company.intraday_today (already on
  // the loaded company doc — no extra read) and fall back to reading
  // companies/{t}/intraday/{today} directly. The audit found /chart 1D
  // was rendering a single dot because it only read EOD rows.
  const intradayDate = company?.intraday_date ?? chartEnd;
  const { data: intradayFetched } = useIntradayDay(short, intradayDate, range === "1D" && !company?.intraday_today?.length);
  const intradayPoints = company?.intraday_today?.length ? company.intraday_today : (intradayFetched ?? []);
  // Drawing tool state — activeTool drives the LeftDrawingRail highlight and
  // the MainCanvas overlay's click-capture mode. Drawings are stored as an
  // append-only list; MainCanvas renders them as SVG marks (dots for anchors,
  // horizontal ReferenceLines for horizontal, dashed lines for trends, etc.).
  const [activeTool, setActiveTool] = useState<string>("crosshair");
  const [drawings, setDrawings] = useState<Array<{ id: string; tool: string; date: string; price: number; label?: string }>>([]);
  const [drawingsVisible, setDrawingsVisible] = useState(true);
  const [drawingsLocked, setDrawingsLocked] = useState(false);
  // Custom-range window. Only consulted when `range === "Custom"`; otherwise
  // the fixed presets in RANGES drive the filter. Persisted per-ticker so
  // switching away and back doesn't nuke the user's selection.
  const customKey = `ws-custom-range-${short}`;
  const [customRange, setCustomRange] = useState<{ start: string; end: string }>(() => {
    if (typeof window === "undefined") return defaultCustomRange();
    try {
      const raw = window.localStorage.getItem(customKey);
      if (raw) return JSON.parse(raw) as { start: string; end: string };
    } catch { /* fall through */ }
    return defaultCustomRange();
  });
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(customKey, JSON.stringify(customRange));
    }
  }, [customRange, customKey]);
  const [chartType, setChartType] = useState<ChartType>("line");
  // Indicator toggles. Each one is a line overlay on the price chart,
  // computed client-side from the visible price series (no extra fetch).
  // Persisted to localStorage so the user's setup survives page reloads,
  // matching TradingView's default behavior.
  const [indicators, setIndicators] = useState<Set<IndicatorKey>>(() => {
    if (typeof window === "undefined") return new Set();
    try {
      const stored = window.localStorage.getItem("ws-indicators");
      return stored ? new Set(JSON.parse(stored) as IndicatorKey[]) : new Set();
    } catch {
      return new Set();
    }
  });
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("ws-indicators", JSON.stringify([...indicators]));
    }
  }, [indicators]);
  const toggleIndicator = (k: IndicatorKey) =>
    setIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });

  // Price alerts — per-ticker, persisted to localStorage. Firebase-side
  // notifications (email/push when the price actually crosses the threshold)
  // are a separate Firebase Function track. For now the alert is visible
  // to the user via a horizontal ReferenceLine on the chart + a badge
  // when the current price has already crossed.
  const alertsKey = `ws-alerts-${short}`;
  const [alerts, setAlerts] = useState<PriceAlert[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const raw = window.localStorage.getItem(alertsKey);
      return raw ? (JSON.parse(raw) as PriceAlert[]) : [];
    } catch {
      return [];
    }
  });
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(alertsKey, JSON.stringify(alerts));
    }
  }, [alerts, alertsKey]);
  const [alertModalOpen, setAlertModalOpen] = useState(false);
  const addAlert = (a: Omit<PriceAlert, "id" | "created_at">) =>
    setAlerts((prev) => [...prev, {
      ...a,
      id: `${Date.now()}-${Math.floor(Math.random() * 9999)}`,
      created_at: new Date().toISOString(),
    }]);
  const deleteAlert = (id: string) => setAlerts((prev) => prev.filter(a => a.id !== id));

  // Undo/Redo history stack. Every state change (chartType, indicators,
  // range, alerts) is snapshotted; Undo walks the stack backwards. Kept
  // shallow (last 20 snapshots) so memory stays bounded and users don't
  // undo across ticker navigations. NOT persisted — a fresh page load
  // starts with an empty history, matching TradingView's behaviour.
  const historyRef = useRef<WsSnapshot[]>([]);
  const historyIdxRef = useRef<number>(-1);
  const [historyVersion, setHistoryVersion] = useState(0);
  // Suppress the snapshot push when the state change is FROM undo/redo
  // itself, otherwise redo would immediately push a new "future" and
  // truncate the redo branch.
  const skipNextSnapshotRef = useRef(false);
  useEffect(() => {
    if (skipNextSnapshotRef.current) {
      skipNextSnapshotRef.current = false;
      return;
    }
    const snap: WsSnapshot = {
      range, chartType,
      indicators: [...indicators],
      alertIds: alerts.map(a => a.id),
    };
    // Drop everything AFTER the current index (branching truncates redo).
    const trimmed = historyRef.current.slice(0, historyIdxRef.current + 1);
    trimmed.push(snap);
    // Cap at 20 entries — drop from the front.
    while (trimmed.length > 20) trimmed.shift();
    historyRef.current = trimmed;
    historyIdxRef.current = trimmed.length - 1;
    setHistoryVersion(v => v + 1);
  }, [range, chartType, indicators, alerts]);

  const applySnapshot = (s: WsSnapshot) => {
    skipNextSnapshotRef.current = true;
    setRange(s.range);
    setChartType(s.chartType);
    setIndicators(new Set(s.indicators));
    // Alert restoration by ID lookup — alerts with IDs no longer in the
    // current set stay dropped. Alerts NEWER than the snapshot get removed.
    setAlerts(prev => prev.filter(a => s.alertIds.includes(a.id)));
  };
  const canUndo = historyIdxRef.current > 0;
  const canRedo = historyIdxRef.current < historyRef.current.length - 1;
  const undo = () => {
    if (!canUndo) return;
    historyIdxRef.current -= 1;
    applySnapshot(historyRef.current[historyIdxRef.current]);
    setHistoryVersion(v => v + 1);
  };
  const redo = () => {
    if (!canRedo) return;
    historyIdxRef.current += 1;
    applySnapshot(historyRef.current[historyIdxRef.current]);
    setHistoryVersion(v => v + 1);
  };
  // Silence 'setHistoryVersion is unused' — we call it to trigger a
  // re-render so the ribbon's Undo/Redo buttons update their disabled
  // state after a step. The version number itself is not read anywhere.
  void historyVersion;
  // Right sidebar collapse — some users want the chart to fill the whole
  // width; others want the watchlist visible alongside. Toggled by the
  // small chevron at the divider. Persisted to localStorage so the
  // preference sticks across navigations.
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return window.localStorage.getItem("ws-sidebar-open") !== "0";
  });
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("ws-sidebar-open", sidebarOpen ? "1" : "0");
    }
  }, [sidebarOpen]);

  // Filter by selected range. Dropdown selector at the bottom of the chart
  // mirrors TradingView's timeframe strip. Custom lets the user bracket
  // the analysis to any start/end pair (drives the Returns Calculator's
  // period as well, since it consumes the same filtered window downstream).
  const visible = useMemo(() => {
    if (!rows.length) return [];
    if (range === "Custom") {
      const { start, end } = customRange;
      return rows.filter((r) => r.date >= start && r.date <= end);
    }
    if (range === "All") return rows;
    if (range === "YTD") {
      const cut = `${new Date().getFullYear()}-01-01`;
      return rows.filter((r) => r.date >= cut);
    }
    const days = RANGES.find((r) => r.key === range)?.days ?? null;
    if (!days || days < 0) return rows;
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - days);
    const iso = cutoff.toISOString().slice(0, 10);
    return rows.filter((r) => r.date >= iso);
  }, [rows, range, customRange]);

  // Span (in days) of what's currently drawn — feeds the date-axis
  // formatter so the tick density matches the window (day+month for short
  // ranges, month+year for multi-year).
  const visibleSpanDays = useMemo(() => {
    if (visible.length < 2) return 30;
    const a = new Date(visible[0].date).getTime();
    const b = new Date(visible[visible.length - 1].date).getTime();
    return Math.max(1, Math.round((b - a) / (24 * 3600 * 1000)));
  }, [visible]);

  // Chart data. Two paths:
  //
  // 1D: use `intradayPoints` if available (company.intraday_today, or a
  //     one-off fetch of companies/{t}/intraday/{today}). Each point becomes
  //     a ChartPoint keyed by its time-of-day string so the tooltip/axis
  //     read "09:45", "10:00", … Indicators don't apply intraday — the
  //     20-day SMA has no meaning at 30-min resolution.
  //
  // Everything else: compute indicators over the FULL price history so
  // SMA 200 has values from bar 200 onwards regardless of which range
  // the user picked, then slice to the visible window. Prior version
  // computed on `visible`, which left any MA with period > 20% of the
  // visible window mostly blank + a stub at the right edge.
  const chartData = useMemo<ChartPoint[]>(
    () => {
      if (range === "1D" && intradayPoints.length > 0) {
        // Defensive filter — legacy intraday_today entries have shown
        // up with missing time or price on a handful of tickers. Any
        // downstream .toFixed / axis formatter would crash the whole
        // chart, so drop malformed points before mapping.
        return intradayPoints
          .filter((p) => p && typeof p.price === "number" && !!p.time)
          .map((p) => ({
            date: p.time,
            price: p.price,
            volume: 0,
            up: true,
          }));
      }
      const fullBase: ChartPoint[] = rows
        .filter((r) => r.c != null && (r.c as number) > 0)
        .map((r) => ({
          date: r.date,
          price: r.c as number,
          volume: (r.v as number | null) ?? 0,
          up: r.pc != null ? (r.c as number) >= (r.pc as number) : true,
        }));
      const fullDecorated = decorateWithIndicators(fullBase, indicators);
      if (!visible.length) return fullDecorated;
      const startDate = visible[0].date;
      const endDate = visible[visible.length - 1].date;
      return fullDecorated.filter(p => p.date >= startDate && p.date <= endDate);
    },
    [range, intradayPoints, rows, visible, indicators],
  );

  // Container ref for fullscreen. Points at the outer workstation wrapper
  // so requestFullscreen() takes the whole ribbon + canvas + sidebar
  // into fullscreen mode, not just the chart.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  useEffect(() => {
    const onChange = () => setIsFullscreen(document.fullscreenElement != null);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const toggleFullscreen = () => {
    if (typeof document === "undefined") return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    } else if (containerRef.current?.requestFullscreen) {
      containerRef.current.requestFullscreen().catch(() => {});
    }
  };

  // Snapshot: capture the chart's SVG and download as PNG. No external
  // dependency — we serialise the SVG, rasterise it via a canvas element,
  // then trigger the browser download. Works in every evergreen browser.
  const chartMountRef = useRef<HTMLDivElement | null>(null);
  const snapshot = () => {
    if (typeof document === "undefined") return;
    const svgs = chartMountRef.current?.querySelectorAll("svg");
    if (!svgs || svgs.length === 0) return;
    // Snap the FIRST svg (price chart). Users rarely want the volume band
    // in isolation; a future improvement could composite both.
    const svg = svgs[0].cloneNode(true) as SVGSVGElement;
    const rect = svgs[0].getBoundingClientRect();
    svg.setAttribute("width", String(rect.width));
    svg.setAttribute("height", String(rect.height));
    const serialised = new XMLSerializer().serializeToString(svg);
    const svgBlob = new Blob([serialised], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(svgBlob);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = rect.width * 2;   // 2x for crisp screenshots
      canvas.height = rect.height * 2;
      const ctx = canvas.getContext("2d");
      if (!ctx) { URL.revokeObjectURL(url); return; }
      ctx.fillStyle = "#FFFFFF";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob((blob) => {
        if (!blob) return;
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `${short}_${new Date().toISOString().slice(0, 10)}.png`;
        a.click();
        URL.revokeObjectURL(a.href);
      }, "image/png");
    };
    img.onerror = () => URL.revokeObjectURL(url);
    img.src = url;
  };

  const latestPrice = latest?.c ?? null;
  const changePct = latest?.pch ?? company?.change_pct_today ?? null;
  const changeAbs = latest?.ch ?? null;

  const pricePeriodMin = chartData.length > 0 ? Math.min(...chartData.map(d => d.price)) : 0;
  const pricePeriodMax = chartData.length > 0 ? Math.max(...chartData.map(d => d.price)) : 0;

  // Bid/ask overlay in the top-left of the canvas. NSE bid-ask spread
  // isn't in our data feed — we mock it as +/- 1 tick from latest as a
  // visual reference. Boxes are non-executable (we're not a broker).
  const bid = latestPrice != null ? Math.max(0.01, latestPrice - 0.05) : null;
  const ask = latestPrice != null ? latestPrice + 0.05 : null;

  return (
    <div
      ref={containerRef}
      // overflow-visible so top-ribbon dropdowns (timeframe, chart type,
      // indicators, layout, hamburger, alerts) aren't clipped. The audit
      // circled every menu as "opens in DOM but invisible" — that clip.
      className="w-full overflow-visible rounded-none border-y"
      style={{ background: COLORS.bg, borderColor: COLORS.border, color: COLORS.text }}
    >
      <TopRibbon
        symbol={short}
        indicators={indicators}
        onToggleIndicator={toggleIndicator}
        isFullscreen={isFullscreen}
        onToggleFullscreen={toggleFullscreen}
        onSnapshot={snapshot}
        alerts={alerts}
        onOpenAlerts={() => setAlertModalOpen(true)}
        onDeleteAlert={deleteAlert}
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={undo}
        onRedo={redo}
        allCompanies={allCompanies}
        company={company}
        latestPrice={latestPrice}
        changeAbs={changeAbs}
        changePct={changePct}
        range={range}
        onRangeChange={setRange}
        chartType={chartType}
        onChartTypeChange={setChartType}
      />

      <div className="relative flex min-h-[480px] sm:min-h-[600px] md:min-h-[720px] lg:min-h-[820px]">
        <LeftDrawingRail
          activeTool={activeTool}
          onActiveToolChange={setActiveTool}
          onClearDrawings={() => setDrawings([])}
          hasDrawings={drawings.length > 0}
          drawingsVisible={drawingsVisible}
          onToggleDrawingsVisible={() => setDrawingsVisible(v => !v)}
          drawingsLocked={drawingsLocked}
          onToggleDrawingsLocked={() => setDrawingsLocked(v => !v)}
        />
        <MainCanvas
          data={chartData}
          latestPrice={latestPrice}
          chartType={chartType}
          bid={bid}
          ask={ask}
          activeIndicators={indicators}
          mountRef={chartMountRef}
          alerts={alerts}
          spanDays={visibleSpanDays}
          activeTool={activeTool}
          drawings={drawings}
          drawingsVisible={drawingsVisible}
          drawingsLocked={drawingsLocked}
          onAddDrawing={(d) => setDrawings(prev => [...prev, d])}
        />

        {/* Collapse toggle sits on the seam between canvas and sidebar
            (or where the sidebar used to be) so it works in both states. */}
        <button
          type="button"
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
          title={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
          className="absolute top-3 z-20 hidden h-8 w-4 items-center justify-center rounded-l lg:flex"
          style={{
            right: sidebarOpen ? 288 : 0, // 72*4=288 (w-72)
            background: COLORS.panel,
            border: `1px solid ${COLORS.border}`,
            borderRight: sidebarOpen ? `1px solid ${COLORS.border}` : "none",
            color: COLORS.muted,
          }}
        >
          <Icon name={sidebarOpen ? "chevron-right" : "chevron-left"} size={12} />
        </button>

        {sidebarOpen && (
          <RightSidebarConnected
            company={company}
            latestPrice={latestPrice}
            changeAbs={changeAbs}
            changePct={changePct}
            periodMin={pricePeriodMin}
            periodMax={pricePeriodMax}
          />
        )}
      </div>

      <BottomTimeframeStrip
        range={range}
        onChange={setRange}
        customRange={customRange}
        onCustomRangeChange={setCustomRange}
      />

      {alertModalOpen && (
        <AlertModal
          symbol={short}
          currentPrice={latestPrice}
          onClose={() => setAlertModalOpen(false)}
          onSave={(a) => { addAlert(a); setAlertModalOpen(false); }}
        />
      )}
    </div>
  );
};

// ─── Top ribbon ─────────────────────────────────────────────────────────────

const TopRibbon: FC<{
  symbol: string;
  allCompanies: CompanyDoc[];
  company: CompanyDoc | null | undefined;
  latestPrice: number | null;
  changeAbs: number | null;
  changePct: number | null;
  range: RangeKey;
  onRangeChange: (r: RangeKey) => void;
  chartType: ChartType;
  onChartTypeChange: (t: ChartType) => void;
  indicators: Set<IndicatorKey>;
  onToggleIndicator: (k: IndicatorKey) => void;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onSnapshot: () => void;
  alerts: PriceAlert[];
  onOpenAlerts: () => void;
  onDeleteAlert: (id: string) => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
}> = ({
  symbol, allCompanies, company, latestPrice, changeAbs, changePct,
  range, onRangeChange, chartType, onChartTypeChange,
  indicators, onToggleIndicator, isFullscreen, onToggleFullscreen, onSnapshot,
  alerts, onOpenAlerts, onDeleteAlert,
  canUndo, canRedo, onUndo, onRedo,
}) => {
  const [searchOpen, setSearchOpen] = useState(false);
  const [chartTypeMenuOpen, setChartTypeMenuOpen] = useState(false);
  const [indicatorsMenuOpen, setIndicatorsMenuOpen] = useState(false);
  const [alertsListOpen, setAlertsListOpen] = useState(false);
  const [appMenuOpen, setAppMenuOpen] = useState(false);
  const [layoutMenuOpen, setLayoutMenuOpen] = useState(false);
  const [addSymbolOpen, setAddSymbolOpen] = useState(false);
  const [addSymbolQuery, setAddSymbolQuery] = useState("");
  const chartTypeRef = useRef<HTMLDivElement | null>(null);
  const indicatorsRef = useRef<HTMLDivElement | null>(null);
  const alertsListRef = useRef<HTMLDivElement | null>(null);
  const appMenuRef = useRef<HTMLDivElement | null>(null);
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const addSymbolRef = useRef<HTMLDivElement | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [rangeMenuOpen, setRangeMenuOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const rangeRef  = useRef<HTMLDivElement>(null);

  // Single mousedown listener that closes every dropdown whose ref is
  // outside the click target. Also clears the add-symbol query so
  // reopening the dropdown starts from a clean input.
  useEffect(() => {
    const h = (e: MouseEvent) => {
      const t = e.target as Node;
      if (chartTypeRef.current && !chartTypeRef.current.contains(t)) setChartTypeMenuOpen(false);
      if (indicatorsRef.current && !indicatorsRef.current.contains(t)) setIndicatorsMenuOpen(false);
      if (alertsListRef.current && !alertsListRef.current.contains(t)) setAlertsListOpen(false);
      if (appMenuRef.current && !appMenuRef.current.contains(t)) setAppMenuOpen(false);
      if (layoutRef.current && !layoutRef.current.contains(t)) setLayoutMenuOpen(false);
      if (addSymbolRef.current && !addSymbolRef.current.contains(t)) {
        setAddSymbolOpen(false);
        setAddSymbolQuery("");
      }
      if (searchRef.current && !searchRef.current.contains(t)) setSearchOpen(false);
      if (rangeRef.current && !rangeRef.current.contains(t)) setRangeMenuOpen(false);
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const searchResults = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return allCompanies.slice(0, 8);
    return allCompanies
      .filter(c => c.short.toLowerCase().includes(q) || c.name.toLowerCase().includes(q))
      .slice(0, 8);
  }, [allCompanies, searchQuery]);

  const changeIsUp = (changePct ?? 0) >= 0;
  const changeColor = changeIsUp ? COLORS.buy : COLORS.sell;

  return (
    <div className="flex flex-col" style={{ borderBottom: `1px solid ${COLORS.border}`, background: COLORS.panel }}>
      {/* Top row: symbol search + timeframe + chart type + tools + right-side utilities.
          overflow-x-auto ONLY on narrow viewports so the toolbar stays reachable
          via horizontal scroll on phones. From md+ we switch to overflow-visible
          so absolute-positioned dropdowns aren't clipped — the audit found
          every dropdown was invisible because overflow-x-auto sets overflow-y
          to auto too, hiding menu items below the ribbon. */}
      <div className="flex items-center gap-1 overflow-x-auto md:overflow-visible px-2 py-1 whitespace-nowrap sm:gap-2 sm:px-3" style={{ borderBottom: `1px solid ${COLORS.border}` }}>
        {/* Hamburger — global app menu */}
        <div ref={appMenuRef} className="relative">
          <IconBtn label="Menu" active={appMenuOpen} onClick={() => setAppMenuOpen(v => !v)}><Icon name="menu" /></IconBtn>
          {appMenuOpen && (
            <div
              className="absolute left-0 top-full z-50 mt-1 w-56 overflow-hidden rounded-md shadow-lg"
              style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            >
              <Link to="/" onClick={() => setAppMenuOpen(false)} className="block px-3 py-1.5 text-xs hover:bg-slate-100" style={{ color: COLORS.text }}>Home</Link>
              <Link to="/companies" onClick={() => setAppMenuOpen(false)} className="block px-3 py-1.5 text-xs hover:bg-slate-100" style={{ color: COLORS.text }}>Companies</Link>
              <Link to="/screener" onClick={() => setAppMenuOpen(false)} className="block px-3 py-1.5 text-xs hover:bg-slate-100" style={{ color: COLORS.text }}>Screener</Link>
              <button
                type="button"
                onClick={() => { onOpenAlerts(); setAppMenuOpen(false); }}
                className="block w-full px-3 py-1.5 text-left text-xs hover:bg-slate-100"
                style={{ color: COLORS.text }}
              >
                Create alert
              </button>
              <button
                type="button"
                onClick={() => { onSnapshot(); setAppMenuOpen(false); }}
                className="block w-full px-3 py-1.5 text-left text-xs hover:bg-slate-100"
                style={{ color: COLORS.text, borderTop: `1px solid ${COLORS.border}` }}
              >
                Download PNG snapshot
              </button>
              <button
                type="button"
                onClick={() => { onToggleFullscreen(); setAppMenuOpen(false); }}
                className="block w-full px-3 py-1.5 text-left text-xs hover:bg-slate-100"
                style={{ color: COLORS.text }}
              >
                {isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
              </button>
            </div>
          )}
        </div>

        {/* Symbol search dropdown */}
        <div ref={searchRef} className="relative">
          <button
            type="button"
            onClick={() => setSearchOpen((v) => !v)}
            className="flex items-center gap-1.5 rounded px-2 py-1 text-sm font-bold"
            style={{ color: COLORS.text, background: searchOpen ? COLORS.bg : "transparent" }}
          >
            <span>{symbol}</span>
            <Icon name="chevron-down" size={12} />
          </button>
          {searchOpen && (
            <div
              className="absolute left-0 top-full z-50 mt-1 w-72 overflow-hidden rounded-md shadow-lg"
              style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            >
              <input
                type="text"
                placeholder="Search NSE listings…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                autoFocus
                className="w-full px-3 py-2 text-sm outline-none"
                style={{ background: COLORS.bg, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}` }}
              />
              <ul className="max-h-72 overflow-y-auto">
                {searchResults.map((c) => (
                  <li key={c.id}>
                    <Link
                      to={`/company/${c.id}`}
                      className="flex items-baseline justify-between gap-3 px-3 py-2 text-xs hover:bg-slate-100"
                      style={{ color: COLORS.text }}
                      onClick={() => setSearchOpen(false)}
                    >
                      <span className="flex items-baseline gap-2">
                        <span className="font-bold">{c.short}</span>
                        <span style={{ color: COLORS.muted }}>{c.name}</span>
                      </span>
                      {c.change_pct_today != null && (
                        <span
                          className="font-mono text-[10px] tabular-nums"
                          style={{ color: c.change_pct_today >= 0 ? COLORS.buy : COLORS.sell }}
                        >
                          {fmtPct(c.change_pct_today)}
                        </span>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Add symbol — quick jump to another ticker */}
        <div ref={addSymbolRef} className="relative">
          <IconBtn label="Add symbol" active={addSymbolOpen} onClick={() => setAddSymbolOpen(v => !v)}>
            <Icon name="plus-circle" />
          </IconBtn>
          {addSymbolOpen && (
            <div
              className="absolute left-0 top-full z-50 mt-1 w-72 overflow-hidden rounded-md shadow-lg"
              style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            >
              <input
                type="text"
                placeholder="Jump to symbol…"
                value={addSymbolQuery}
                onChange={(e) => setAddSymbolQuery(e.target.value)}
                autoFocus
                className="w-full px-3 py-2 text-sm outline-none"
                style={{ background: COLORS.bg, color: COLORS.text, borderBottom: `1px solid ${COLORS.border}` }}
              />
              <ul className="max-h-72 overflow-y-auto">
                {allCompanies
                  .filter(c => {
                    const q = addSymbolQuery.trim().toLowerCase();
                    if (!q) return true;
                    return c.short.toLowerCase().includes(q) || c.name.toLowerCase().includes(q);
                  })
                  .slice(0, 8)
                  .map(c => (
                    <li key={c.id}>
                      <Link
                        to={`/chart/${c.ticker ?? c.short}`}
                        className="flex items-baseline justify-between gap-3 px-3 py-2 text-xs hover:bg-slate-100"
                        style={{ color: COLORS.text }}
                        onClick={() => { setAddSymbolOpen(false); setAddSymbolQuery(""); }}
                      >
                        <span className="flex items-baseline gap-2">
                          <span className="font-bold">{c.short}</span>
                          <span style={{ color: COLORS.muted }}>{c.name}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>

        {/* Timeframe */}
        <div ref={rangeRef} className="relative">
          <button
            type="button"
            onClick={() => setRangeMenuOpen((v) => !v)}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold"
            style={{ color: COLORS.text, background: rangeMenuOpen ? COLORS.bg : "transparent" }}
          >
            {range}
            <Icon name="chevron-down" size={10} />
          </button>
          {rangeMenuOpen && (
            <div
              className="absolute left-0 top-full z-50 mt-1 w-24 overflow-hidden rounded-md shadow-lg"
              style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            >
              {RANGES.map((r) => (
                <button
                  key={r.key}
                  type="button"
                  onClick={() => { onRangeChange(r.key); setRangeMenuOpen(false); }}
                  className="block w-full px-3 py-1.5 text-left text-xs hover:bg-slate-100"
                  style={{ color: r.key === range ? COLORS.accent : COLORS.text, fontWeight: r.key === range ? 700 : 500 }}
                >
                  {r.key}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Chart type dropdown — click opens a menu with the three
            variants we actually support (line / area / columns). */}
        <div ref={chartTypeRef} className="relative">
          <button
            type="button"
            onClick={() => setChartTypeMenuOpen((v) => !v)}
            className="flex items-center gap-1 rounded p-1"
            style={{
              color: chartTypeMenuOpen ? COLORS.accent : COLORS.muted,
              background: chartTypeMenuOpen ? COLORS.bg : "transparent",
            }}
            title="Chart type"
          >
            <Icon name={CHART_TYPES.find(t => t.key === chartType)?.icon ?? "line-chart"} />
            <Icon name="chevron-down" size={10} />
          </button>
          {chartTypeMenuOpen && (
            <div
              className="absolute left-0 top-full z-50 mt-1 w-40 overflow-hidden rounded-md shadow-lg"
              style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            >
              {CHART_TYPES.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => { onChartTypeChange(t.key); setChartTypeMenuOpen(false); }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-slate-100"
                  style={{
                    color: t.key === chartType ? COLORS.accent : COLORS.text,
                    fontWeight: t.key === chartType ? 700 : 500,
                  }}
                >
                  <Icon name={t.icon} size={14} />
                  {t.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Indicators dropdown — checkboxes for the seven overlays we
            compute client-side. State persists across page reloads. */}
        <div ref={indicatorsRef} className="relative">
          <button
            type="button"
            onClick={() => setIndicatorsMenuOpen((v) => !v)}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold hover:bg-slate-100"
            style={{
              color: indicators.size > 0 ? COLORS.accent : COLORS.text,
              background: indicatorsMenuOpen ? COLORS.bg : "transparent",
            }}
            title="Toggle indicators"
          >
            <Icon name="grid" size={14} />
            <span>Indicators</span>
            {indicators.size > 0 && (
              <span
                className="rounded-full px-1.5 text-[9px] font-bold text-white"
                style={{ background: COLORS.accent }}
              >
                {indicators.size}
              </span>
            )}
          </button>
          {indicatorsMenuOpen && (
            <div
              className="absolute left-0 top-full z-50 mt-1 w-56 overflow-hidden rounded-md shadow-lg"
              style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            >
              <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: COLORS.hint, borderBottom: `1px solid ${COLORS.border}` }}>
                Overlays
              </div>
              {INDICATORS.map((ind) => (
                <button
                  key={ind.key}
                  type="button"
                  onClick={() => onToggleIndicator(ind.key)}
                  className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-xs hover:bg-slate-100"
                  style={{ color: COLORS.text }}
                >
                  <span className="flex items-center gap-2">
                    <span
                      className="h-0.5 w-4 rounded"
                      style={{ background: ind.color }}
                    />
                    {ind.label}
                  </span>
                  <span
                    className="flex h-4 w-4 items-center justify-center rounded border"
                    style={{
                      borderColor: indicators.has(ind.key) ? COLORS.accent : COLORS.border,
                      background: indicators.has(ind.key) ? COLORS.accent : COLORS.panel,
                    }}
                  >
                    {indicators.has(ind.key) && (
                      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="3">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </span>
                </button>
              ))}
              <button
                type="button"
                onClick={() => {
                  INDICATORS.forEach(i => indicators.has(i.key) && onToggleIndicator(i.key));
                  setIndicatorsMenuOpen(false);
                }}
                className="w-full px-3 py-1.5 text-left text-[10px] hover:bg-slate-100"
                style={{ color: COLORS.hint, borderTop: `1px solid ${COLORS.border}` }}
              >
                Clear all
              </button>
            </div>
          )}
        </div>

        {/* Templates: save/load workstation config (chartType + indicators + range) to localStorage. */}
        <span className="hidden md:inline-flex">
          <TextBtn
            icon="layers"
            title="Save the current chart config as a template"
            onClick={() => {
              const name = typeof window !== "undefined" ? window.prompt("Save chart template as:") : null;
              if (!name) return;
              try {
                const raw = window.localStorage.getItem("ws-templates");
                const list = raw ? JSON.parse(raw) as Array<{ name: string; range: RangeKey; chartType: ChartType; indicators: IndicatorKey[] }> : [];
                list.push({ name, range, chartType, indicators: [...indicators] });
                window.localStorage.setItem("ws-templates", JSON.stringify(list));
                window.alert(`Template "${name}" saved.`);
              } catch {
                window.alert("Could not save template.");
              }
            }}
          >Templates</TextBtn>
        </span>

        {/* Alert — click opens the create modal; chevron opens the
            existing-alerts panel. Active count shown as a badge. */}
        <div ref={alertsListRef} className="relative flex items-center">
          <button
            type="button"
            onClick={onOpenAlerts}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold hover:bg-slate-100"
            style={{ color: alerts.length > 0 ? COLORS.accent : COLORS.text }}
            title="Set a price alert"
          >
            <Icon name="bell" size={14} />
            <span>Alert</span>
            {alerts.length > 0 && (
              <span
                className="rounded-full px-1.5 text-[9px] font-bold text-white"
                style={{ background: COLORS.accent }}
              >
                {alerts.length}
              </span>
            )}
          </button>
          {alerts.length > 0 && (
            <button
              type="button"
              onClick={() => setAlertsListOpen((v) => !v)}
              className="rounded p-0.5 hover:bg-slate-100"
              style={{ color: COLORS.muted }}
              title="View existing alerts"
            >
              <Icon name="chevron-down" size={10} />
            </button>
          )}
          {alertsListOpen && alerts.length > 0 && (
            <div
              className="absolute left-0 top-full z-50 mt-1 w-64 overflow-hidden rounded-md shadow-lg"
              style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
            >
              <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wider" style={{ color: COLORS.hint, borderBottom: `1px solid ${COLORS.border}` }}>
                Active alerts on {symbol}
              </div>
              {alerts.map((a) => {
                const crossed = latestPrice != null
                  && ((a.direction === "above" && latestPrice >= a.threshold)
                    || (a.direction === "below" && latestPrice <= a.threshold));
                return (
                  <div
                    key={a.id}
                    className="flex items-center justify-between gap-2 px-3 py-1.5 text-xs hover:bg-slate-50"
                    style={{ color: COLORS.text }}
                  >
                    <span className="flex flex-col">
                      <span className="font-mono tabular-nums">
                        {a.direction === "above" ? "▲" : "▼"} KES {a.threshold.toFixed(2)}
                      </span>
                      {crossed && (
                        <span className="text-[9px]" style={{ color: COLORS.buy }}>
                          ● Triggered
                        </span>
                      )}
                      {a.note && (
                        <span className="text-[9px]" style={{ color: COLORS.hint }}>{a.note}</span>
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={() => onDeleteAlert(a.id)}
                      title="Delete alert"
                      className="rounded p-1 hover:bg-slate-100"
                      style={{ color: COLORS.muted }}
                    >
                      <Icon name="trash" size={12} />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <span className="hidden md:inline-flex">
          <TextBtn
            icon="rewind"
            title="Historical replay — coming soon"
            onClick={() => window.alert("Historical replay (step-through backtesting) ships in a follow-up. For now, use the timeframe strip to bracket a window.")}
          >Replay</TextBtn>
        </span>

        {/* History controls — hidden below md. Both grey out when the
            history stack has no more steps in that direction. */}
        <div className="ml-1 hidden items-center gap-0.5 md:flex">
          <button
            type="button"
            onClick={onUndo}
            disabled={!canUndo}
            title="Undo"
            className="flex h-7 w-7 items-center justify-center rounded hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
            style={{ color: COLORS.muted }}
          >
            <Icon name="undo" />
          </button>
          <button
            type="button"
            onClick={onRedo}
            disabled={!canRedo}
            title="Redo"
            className="flex h-7 w-7 items-center justify-center rounded hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
            style={{ color: COLORS.muted }}
          >
            <Icon name="redo" />
          </button>
        </div>

        {/* Right-side utilities — pushed to the right with ml-auto. Trade
            and Publish (the two CTA buttons) stay visible; less-critical
            icon buttons hide below lg. */}
        <div className="ml-auto flex items-center gap-1">
          {/* Layout — opens a coming-soon multi-pane preview menu */}
          <span className="hidden lg:inline-flex">
            <div ref={layoutRef} className="relative">
              <IconBtn label="Layout" active={layoutMenuOpen} onClick={() => setLayoutMenuOpen(v => !v)}>
                <Icon name="layout" />
              </IconBtn>
              {layoutMenuOpen && (
                <div
                  className="absolute right-0 top-full z-50 mt-1 w-44 overflow-hidden rounded-md shadow-lg"
                  style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }}
                >
                  <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider" style={{ color: COLORS.hint }}>Layout</div>
                  <button type="button" onClick={() => setLayoutMenuOpen(false)} className="block w-full px-3 py-1.5 text-left text-xs hover:bg-slate-100" style={{ color: COLORS.accent }}>Single chart (active)</button>
                  <button type="button" disabled className="block w-full px-3 py-1.5 text-left text-xs opacity-40" style={{ color: COLORS.text }} title="Coming soon">2 up · horizontal</button>
                  <button type="button" disabled className="block w-full px-3 py-1.5 text-left text-xs opacity-40" style={{ color: COLORS.text }} title="Coming soon">2 up · vertical</button>
                  <button type="button" disabled className="block w-full px-3 py-1.5 text-left text-xs opacity-40" style={{ color: COLORS.text }} title="Coming soon">4 up · grid</button>
                </div>
              )}
            </div>
          </span>
          {/* Save — persist workstation config to localStorage */}
          <span className="hidden lg:inline-flex">
            <TextBtn
              icon="save"
              title="Save the current chart config"
              onClick={() => {
                try {
                  window.localStorage.setItem(`ws-saved-${symbol}`, JSON.stringify({ range, chartType, indicators: [...indicators], savedAt: new Date().toISOString() }));
                  window.alert(`Saved current ${symbol} config to this browser.`);
                } catch {
                  window.alert("Could not save.");
                }
              }}
            >Save</TextBtn>
          </span>
          {/* Alerts panel — reuses onOpenAlerts (same UX as the left bell) */}
          <span className="hidden xl:inline-flex">
            <IconBtn label="Alerts panel" onClick={onOpenAlerts}><Icon name="bell" /></IconBtn>
          </span>
          {/* Trading panel — explicit 'not a broker' notice per COLORS.sell comment on line 584 */}
          <span className="hidden xl:inline-flex">
            <IconBtn
              label="Trading panel — broker integration not available"
              disabled
            ><Icon name="briefcase" /></IconBtn>
          </span>
          {/* Fullscreen: uses HTMLElement.requestFullscreen on the outer
              workstation container. `isFullscreen` flips the icon so the
              user sees they can exit. */}
          <button
            type="button"
            onClick={onToggleFullscreen}
            title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
            className="flex h-7 w-7 items-center justify-center rounded hover:bg-slate-100"
            style={{ color: isFullscreen ? COLORS.accent : COLORS.muted }}
          >
            <Icon name={isFullscreen ? "minimize" : "maximize"} />
          </button>
          {/* Snapshot: rasterises the price SVG and triggers a PNG download. */}
          <button
            type="button"
            onClick={onSnapshot}
            title="Download PNG snapshot"
            className="hidden h-7 w-7 items-center justify-center rounded hover:bg-slate-100 md:flex"
            style={{ color: COLORS.muted }}
          >
            <Icon name="camera" />
          </button>
          <button
            type="button"
            disabled
            title="NSE Intelligence is not a broker — connect a partner broker to trade"
            className="hidden rounded px-3 py-1 text-xs font-bold md:inline-block disabled:cursor-not-allowed disabled:opacity-50"
            style={{ color: COLORS.text, background: COLORS.bg, border: `1px solid ${COLORS.border}` }}
          >
            Trade
          </button>
          <button
            type="button"
            onClick={() => window.alert(`Publishing trade ideas about ${symbol} to the community feed ships next. Meanwhile, use Snapshot (camera icon) to export the chart as PNG.`)}
            title="Publish a trading idea about this ticker"
            className="rounded px-3 py-1 text-xs font-bold text-white"
            style={{ background: COLORS.accent }}
          >
            Publish
          </button>
        </div>
      </div>

      {/* Sub-header: company name · timeframe · exchange · price.
          Wraps on mobile so a long company name doesn't force horizontal
          scroll; on md+ everything sits in a single row. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-2 py-1 text-[11px] sm:px-3 sm:py-1.5 sm:text-xs">
        <span className="flex items-center gap-2">
          <span style={{ color: COLORS.orange }}>●</span>
          <span className="font-semibold" style={{ color: COLORS.text }}>
            {company?.name ?? "…"}{" "}
            <span className="hidden sm:inline" style={{ color: COLORS.muted }}>
              · {range} · NSEKE
            </span>
          </span>
        </span>
        {latestPrice != null && (
          <span className="flex items-center gap-2 font-mono tabular-nums" style={{ color: changeColor }}>
            <span>{latestPrice.toFixed(2)}</span>
            {changeAbs != null && (
              <span>{changeAbs >= 0 ? "+" : ""}{changeAbs.toFixed(2)}</span>
            )}
            {changePct != null && (
              <span>({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)</span>
            )}
          </span>
        )}
      </div>
    </div>
  );
};

// ─── Left drawing rail ──────────────────────────────────────────────────────
// Icons are visual-only for this shipment. A real drawing engine (persist to
// Firestore, hit-testing, resize handles) is a separate multi-day track.
// Click on any icon shows a small "coming soon" tooltip via native title.

const DRAWING_TOOLS: { name: string; label: string }[] = [
  { name: "crosshair",     label: "Crosshair (default)" },
  { name: "trend-line",    label: "Trendline" },
  { name: "channel",       label: "Parallel channel" },
  { name: "fib",           label: "Fibonacci retracement" },
  { name: "brush",         label: "Freehand brush" },
  { name: "text",          label: "Text" },
  { name: "pattern",       label: "Pattern overlays" },
  { name: "ruler",         label: "Prediction / risk-reward ruler" },
  { name: "zoom",          label: "Zoom in / out" },
  { name: "magnet",        label: "Magnet mode" },
  { name: "lock",          label: "Lock drawings" },
  { name: "eye-off",       label: "Hide drawings" },
  { name: "trash",         label: "Delete all" },
];

const LeftDrawingRail: FC<{
  activeTool: string;
  onActiveToolChange: (t: string) => void;
  onClearDrawings: () => void;
  hasDrawings: boolean;
  drawingsVisible: boolean;
  onToggleDrawingsVisible: () => void;
  drawingsLocked: boolean;
  onToggleDrawingsLocked: () => void;
}> = ({ activeTool, onActiveToolChange, onClearDrawings, hasDrawings, drawingsVisible, onToggleDrawingsVisible, drawingsLocked, onToggleDrawingsLocked }) => {
  // Rail is hidden below md; drawing tools drop markers on the chart when
  // active. Trash is a one-shot action (never becomes the active tool),
  // lock/eye-off/magnet are toggles that flip their own state and don't
  // change the active pointer mode.
  return (
    <div
      className="hidden flex-col items-center gap-0.5 py-2 md:flex"
      style={{ background: COLORS.panel, borderRight: `1px solid ${COLORS.border}`, width: 40 }}
    >
      {DRAWING_TOOLS.map((tool) => {
        const isToggle = tool.name === "lock" || tool.name === "eye-off" || tool.name === "magnet";
        const isOneShot = tool.name === "trash";
        const isActive = !isOneShot && !isToggle && activeTool === tool.name;
        const toggleOn =
          (tool.name === "lock" && drawingsLocked) ||
          (tool.name === "eye-off" && !drawingsVisible);
        // eye-off shows an open-eye icon when drawings are hidden (state
        // indicator) and a crossed-out eye when drawings are visible.
        const iconName = tool.name === "eye-off"
          ? (drawingsVisible ? "eye-off" : "eye")
          : tool.name;
        const magnetDisabled = tool.name === "magnet";
        const title = magnetDisabled ? "Magnet — coming soon" : tool.label;
        return (
          <button
            key={tool.name}
            type="button"
            title={title}
            disabled={(isOneShot && !hasDrawings) || magnetDisabled}
            onClick={() => {
              if (isOneShot) {
                if (hasDrawings && typeof window !== "undefined" && window.confirm("Delete all drawings on this chart?")) {
                  onClearDrawings();
                }
                return;
              }
              if (tool.name === "lock") { onToggleDrawingsLocked(); return; }
              if (tool.name === "eye-off") { onToggleDrawingsVisible(); return; }
              if (tool.name === "magnet") { /* future: snap-to-OHLC toggle */ return; }
              onActiveToolChange(tool.name);
            }}
            className="flex h-8 w-8 items-center justify-center rounded disabled:cursor-not-allowed disabled:opacity-30"
            style={{
              background: isActive || toggleOn ? COLORS.bg : "transparent",
              color: isActive || toggleOn ? COLORS.accent : COLORS.muted,
            }}
          >
            <Icon name={iconName} size={16} />
          </button>
        );
      })}
    </div>
  );
};

// ─── Main canvas ────────────────────────────────────────────────────────────

interface Drawing { id: string; tool: string; date: string; price: number; label?: string }

const MainCanvas: FC<{
  data: ChartPoint[];
  latestPrice: number | null;
  chartType: ChartType;
  bid: number | null;
  ask: number | null;
  activeIndicators: Set<IndicatorKey>;
  mountRef: React.RefObject<HTMLDivElement | null>;
  alerts: PriceAlert[];
  spanDays: number;
  activeTool: string;
  drawings: Drawing[];
  drawingsVisible: boolean;
  drawingsLocked: boolean;
  onAddDrawing: (d: Drawing) => void;
}> = ({ data, latestPrice, chartType, bid, ask, activeIndicators, mountRef, alerts, spanDays, activeTool, drawings, drawingsVisible, drawingsLocked, onAddDrawing }) => {
  const handleChartClick = (state: unknown) => {
    if (drawingsLocked) {
      if (activeTool !== "crosshair" && activeTool !== "zoom" && typeof window !== "undefined") {
        window.alert("Drawings are locked. Click the lock icon in the left rail to unlock.");
      }
      return;
    }
    // crosshair and zoom intentionally no-op on click (crosshair is the
    // default hover mode; zoom's wheel/drag implementation is deferred).
    // Every other tool — including pattern — drops an anchor.
    if (activeTool === "crosshair" || activeTool === "zoom") return;
    const s = state as { activeLabel?: string; activePayload?: Array<{ payload?: ChartPoint }> } | null;
    if (!s || !s.activeLabel || !s.activePayload || !s.activePayload[0]?.payload) return;
    const p = s.activePayload[0].payload;
    let label: string | undefined;
    if (activeTool === "text") {
      const entered = typeof window !== "undefined" ? window.prompt("Label:") : null;
      if (!entered) return;
      label = entered;
    }
    onAddDrawing({
      id: `${Date.now()}-${Math.floor(Math.random() * 9999)}`,
      tool: activeTool,
      date: p.date,
      price: p.price,
      label,
    });
  };
  const totalVol = useMemo(() => data.reduce((a, d) => a + d.volume, 0), [data]);

  // Volume-band scale. Sort non-zero volumes and take the 98th percentile
  // as the y-axis cap; a single outlier (off-market block trade, corrections)
  // otherwise crushes every bar to <1 px. Bars above the cap render at the
  // cap height with a hatched fill so the eye reads "value truncated".
  // Data has volumeDisplay = min(volume, cap) computed here rather than in
  // decorateWithIndicators because it depends on the visible window.
  const volumeAxisCap = useMemo(() => {
    const vols = data.map(d => d.volume).filter(v => v > 0).sort((a, b) => a - b);
    if (vols.length === 0) return 0;
    // Ceil so tiny series (< 50 pts) still get a real p98 slot.
    const idx = Math.min(vols.length - 1, Math.ceil(vols.length * 0.98) - 1);
    const cap = vols[Math.max(0, idx)];
    // 15% headroom so tallest bar isn't flush with the top border.
    return cap * 1.15;
  }, [data]);
  const cappedData = useMemo(() => data.map(d => ({
    ...d,
    volumeDisplay: volumeAxisCap > 0 && d.volume > volumeAxisCap ? volumeAxisCap : d.volume,
  })), [data, volumeAxisCap]);

  return (
    <div ref={mountRef} className="relative flex-1 overflow-hidden min-h-[480px] sm:min-h-[600px] md:min-h-[720px] lg:min-h-[820px]" style={{ background: COLORS.panel }}>
      {/* Bid/ask execution overlay (visual only — we're not a broker).
          Tighter padding on mobile so it doesn't dominate the small canvas. */}
      {latestPrice != null && bid != null && ask != null && (
        <div className="absolute left-1.5 top-1.5 z-10 flex items-center gap-0.5 font-mono text-[10px] sm:left-2 sm:top-2 sm:gap-1 sm:text-[11px]">
          <span
            className="rounded px-1.5 py-0.5 text-white sm:px-2 sm:py-1"
            style={{ background: COLORS.sell }}
          >
            <div className="text-[8px] leading-none opacity-90 sm:text-[9px]">SELL</div>
            <div className="font-bold tabular-nums">{bid.toFixed(2)}</div>
          </span>
          <span className="hidden rounded px-1 py-0.5 text-[9px] sm:inline sm:px-1.5 sm:text-[10px]" style={{ background: COLORS.bg, color: COLORS.muted }}>
            {(ask - bid).toFixed(2)}
          </span>
          <span
            className="rounded px-1.5 py-0.5 text-white sm:px-2 sm:py-1"
            style={{ background: COLORS.accent }}
          >
            <div className="text-[8px] leading-none opacity-90 sm:text-[9px]">BUY</div>
            <div className="font-bold tabular-nums">{ask.toFixed(2)}</div>
          </span>
        </div>
      )}

      {/* Volume label top-left under bid-ask */}
      <div className="absolute left-1.5 top-14 z-10 text-[10px] sm:left-2 sm:top-16 sm:text-[11px]" style={{ color: COLORS.muted }}>
        Vol{" "}
        <span className="font-mono font-semibold" style={{ color: COLORS.text }}>
          {fmtCompact(totalVol)}
        </span>
      </div>

      {/* Chart area — price on top 85%, volume on bottom 15%. Two
          separate charts so the volume bars can't overlap the price
          line, and so the price line has a proper Y-axis scale. */}
      <div className="flex h-full w-full flex-col">
        {/* Price band — 85% */}
        <div style={{ flex: "1 1 85%" }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={data}
              margin={{ top: 8, right: 68, bottom: 0, left: 0 }}
              syncId="ws-price-vol"
              onClick={handleChartClick}
              style={{ cursor: drawingsLocked ? "not-allowed" : "crosshair" }}
            >
              <CartesianGrid
                strokeDasharray="1 4"
                stroke={COLORS.grid}
                vertical
                horizontal
              />
              <XAxis
                dataKey="date"
                tick={false}
                axisLine={{ stroke: COLORS.border }}
                tickLine={false}
                height={0}
              />
              <YAxis
                orientation="right"
                tick={{ fontSize: 11, fill: COLORS.muted }}
                tickFormatter={(v: number) => v.toFixed(2)}
                domain={["dataMin - 0.3", "dataMax + 0.3"]}
                stroke={COLORS.border}
                width={62}
              />
              <Tooltip
                contentStyle={{
                  background: COLORS.panel,
                  border: `1px solid ${COLORS.border}`,
                  fontSize: 12,
                  color: COLORS.text,
                  borderRadius: 4,
                }}
                formatter={(value, name, entry) => {
                  // Every series gets a readable KES-formatted value and a
                  // human label instead of the raw key. Prior tooltip showed
                  // "bb_lower : 26.75347033187166" — the audit flagged this
                  // as unreadable; every overlay now prints via fmtPrice.
                  const v = typeof value === "number" ? value : Number(value);
                  const label = TOOLTIP_LABELS[String(name)] ?? String(name);
                  if (name === "price") {
                    const vol = (entry?.payload as ChartPoint | undefined)?.volume;
                    const volLine = vol != null ? ` · Vol ${fmtCompact(vol)}` : "";
                    return [`KES ${fmtPrice(v)}${volLine}`, label];
                  }
                  return [`KES ${fmtPrice(v)}`, label];
                }}
                labelFormatter={(d) => formatTooltipDate(String(d))}
              />
              <defs>
                <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"   stopColor={COLORS.priceLine} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={COLORS.priceLine} stopOpacity={0} />
                </linearGradient>
              </defs>

              {/* Indicator overlays FIRST so the price line renders on top.
                  Each one is nullable — Recharts skips null points instead
                  of drawing a straight line to 0. */}
              {activeIndicators.has("sma20") && (
                <Line type="monotone" dataKey="sma20"  stroke="#F59E0B" strokeWidth={1.4} dot={false} isAnimationActive={false} connectNulls={false} />
              )}
              {activeIndicators.has("sma50") && (
                <Line type="monotone" dataKey="sma50"  stroke="#38BDF8" strokeWidth={1.4} dot={false} isAnimationActive={false} connectNulls={false} />
              )}
              {activeIndicators.has("sma200") && (
                <Line type="monotone" dataKey="sma200" stroke="#A78BFA" strokeWidth={1.4} dot={false} isAnimationActive={false} connectNulls={false} />
              )}
              {activeIndicators.has("ema12") && (
                <Line type="monotone" dataKey="ema12"  stroke="#34D399" strokeWidth={1.4} dot={false} isAnimationActive={false} connectNulls={false} />
              )}
              {activeIndicators.has("ema26") && (
                <Line type="monotone" dataKey="ema26"  stroke="#FB923C" strokeWidth={1.4} dot={false} isAnimationActive={false} connectNulls={false} />
              )}
              {activeIndicators.has("bb") && (
                <>
                  <Line type="monotone" dataKey="bb_upper" stroke="#94A3B8" strokeWidth={1} strokeDasharray="3 3" dot={false} isAnimationActive={false} connectNulls={false} />
                  <Line type="monotone" dataKey="bb_mid"   stroke="#94A3B8" strokeWidth={1} dot={false} isAnimationActive={false} connectNulls={false} />
                  <Line type="monotone" dataKey="bb_lower" stroke="#94A3B8" strokeWidth={1} strokeDasharray="3 3" dot={false} isAnimationActive={false} connectNulls={false} />
                </>
              )}
              {activeIndicators.has("vwap") && (
                <Line type="monotone" dataKey="vwap"   stroke="#EC4899" strokeWidth={1.4} dot={false} isAnimationActive={false} connectNulls={false} />
              )}

              {/* Primary price series. Columns type renders as a bar
                  chart at the bottom (see the outer BarChart in a
                  fallback path below); for line and area we render the
                  Line here. */}
              {chartType !== "columns" && (
                <Line
                  type="monotone"
                  dataKey="price"
                  stroke={COLORS.priceLine}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                  fill={chartType === "area" ? "url(#priceFill)" : undefined}
                />
              )}
              {chartType === "columns" && (
                // In columns mode, render tall thin bars via a Line
                // component with a custom shape. Simpler alternative:
                // switch the outer chart to BarChart when in this mode,
                // but that would double the code path. This stays inside
                // LineChart via a hack — flip the stroke to zero and use
                // vertical segments via dot rendering.
                // Cleanest: render as a plain Line with reduced opacity
                // so users see it while we develop true columns support.
                <Line
                  type="stepAfter"
                  dataKey="price"
                  stroke={COLORS.priceLine}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              )}
              {latestPrice != null && (
                <ReferenceLine
                  y={latestPrice}
                  stroke={COLORS.livePrice}
                  strokeDasharray="2 3"
                  strokeWidth={1}
                  label={{
                    value: latestPrice.toFixed(2),
                    fill: "#FFFFFF",
                    fontSize: 11,
                    fontWeight: 700,
                    position: "right",
                    offset: 4,
                  } as unknown as string}
                />
              )}

              {/* Price alerts render as horizontal dashed lines with a
                  right-side label. Colour uses BUY (green) for below-
                  threshold triggers and SELL (red) for above-threshold —
                  matches the mental model of 'below = accumulate, above
                  = take profit'. */}
              {alerts.map((a) => (
                <ReferenceLine
                  key={a.id}
                  y={a.threshold}
                  stroke={a.direction === "above" ? COLORS.sell : COLORS.buy}
                  strokeDasharray="4 4"
                  strokeWidth={1}
                  label={{
                    value: `${a.direction === "above" ? "▲" : "▼"} ${a.threshold.toFixed(2)}`,
                    fill: "#FFFFFF",
                    fontSize: 10,
                    fontWeight: 700,
                    position: "left",
                    offset: 4,
                  } as unknown as string}
                />
              ))}

              {/* User drawings — each drop-anchor becomes a horizontal
                  ReferenceLine at that price. Trendline/fib/ruler take
                  multiple anchors and render as chained horizontals; a full
                  slope engine ships in a follow-up. */}
              {drawingsVisible && drawings.map((d) => (
                <ReferenceLine
                  key={d.id}
                  y={d.price}
                  stroke={COLORS.accent}
                  strokeDasharray={d.tool === "fib" ? "1 3" : "2 4"}
                  strokeWidth={1}
                  label={{
                    value: d.label ?? `${d.tool} @ ${d.price.toFixed(2)}`,
                    fill: COLORS.accent,
                    fontSize: 9,
                    fontWeight: 600,
                    position: "insideTopRight",
                    offset: 4,
                  } as unknown as string}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Volume band — 15%. Axis is capped at the 98th percentile of the
            visible window's volumes so a single outlier (e.g. an off-market
            block trade ~500x median) can't crush every other bar to <1 px.
            Bars above the cap render at the cap height as `volumeDisplay`;
            the true value still lives on `volume` for the tooltip. */}
        <div
          style={{ flex: "1 1 15%", borderTop: `1px solid ${COLORS.border}` }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={cappedData}
              margin={{ top: 4, right: 68, bottom: 4, left: 0 }}
              syncId="ws-price-vol"
              barCategoryGap={1}
            >
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: COLORS.muted }}
                tickFormatter={(d: string) => formatAxisDate(d, spanDays)}
                interval="preserveStartEnd"
                minTickGap={60}
                stroke={COLORS.border}
              />
              <YAxis
                orientation="right"
                tick={false}
                axisLine={false}
                tickLine={false}
                domain={[0, volumeAxisCap]}
                width={62}
              />
              {/* Volume tooltip removed — the price LineChart's tooltip
                  drives both bands via syncId="ws-price-vol", and a second
                  Tooltip inside the 15%-tall volume band was pinning to the
                  strip's top edge (reading as 'stuck bottom-left'). */}
              <Bar
                dataKey="volumeDisplay"
                isAnimationActive={false}
                maxBarSize={12}
              >
                {cappedData.map((d, i) => {
                  const isCapped = volumeAxisCap > 0 && d.volume > volumeAxisCap;
                  return (
                    <Cell
                      key={i}
                      // Capped outliers get a lighter fill + white stroke so
                      // the eye reads "value truncated, tooltip has the real
                      // number" instead of "this is genuinely the tallest bar".
                      fill={d.volume > 0 ? (d.up ? COLORS.volUp : COLORS.volDown) : "transparent"}
                      fillOpacity={isCapped ? 0.55 : 1}
                      stroke={isCapped ? "#FFFFFF" : "none"}
                      strokeDasharray={isCapped ? "2 2" : undefined}
                      strokeWidth={isCapped ? 1 : 0}
                    />
                  );
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Centered low-opacity brand watermark (behind the chart, pointer-events off) */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <span
          className="select-none font-black tracking-[0.15em]"
          style={{ fontSize: "clamp(28px, 5vw, 64px)", color: COLORS.text, opacity: 0.05 }}
        >
          NSE INTELLIGENCE
        </span>
      </div>
      {/* Subtle brand tag pinned bottom-right so it never lands under a tooltip */}
      <div className="pointer-events-none absolute bottom-2 right-4 flex items-center gap-1 text-[10px]" style={{ color: COLORS.hint }}>
        <span className="font-bold" style={{ color: COLORS.accent }}>NSE</span> Intelligence
      </div>
    </div>
  );
};

// ─── Right sidebar ──────────────────────────────────────────────────────────

// Thin wrapper that fetches Kenya watchlist data (NSE indices from
// market_overview + NSE stocks from companies mirror) and passes it in.
// Kept separate so the RightSidebar render function stays testable with
// static inputs.
const RightSidebarConnected: FC<{
  company: CompanyDoc | null | undefined;
  latestPrice: number | null;
  changeAbs: number | null;
  changePct: number | null;
  periodMin: number;
  periodMax: number;
}> = (props) => {
  const { data: market } = useMarketOverview();
  const { data: companies } = useCompanies();
  return (
    <RightSidebar
      {...props}
      indexReadings={market?.indices}
      companies={companies}
    />
  );
};

const RightSidebar: FC<{
  company: CompanyDoc | null | undefined;
  latestPrice: number | null;
  changeAbs: number | null;
  changePct: number | null;
  periodMin: number;
  periodMax: number;
  indexReadings: Record<string, IndexReading> | undefined;
  companies: CompanyDoc[] | undefined;
}> = ({ company, latestPrice, changeAbs, changePct, periodMin, periodMax, indexReadings, companies }) => {
  const isUp = (changePct ?? 0) >= 0;
  const changeColor = isUp ? COLORS.buy : COLORS.sell;

  // Compose two watchlist sections from real data:
  //   INDICES: NSE 20/NASI/etc. from today's market_overview doc
  //   STOCKS:  hand-picked NSE tickers, prices from the companies feed
  //            (which already merges the RTDB prices_latest mirror)
  const stockRows = useMemo(() => {
    if (!companies?.length) return [];
    const byId = new Map(companies.map((c) => [c.id, c]));
    return KENYA_WATCHLIST_STOCKS
      .map((short) => byId.get(short))
      .filter((c): c is CompanyDoc => !!c);
  }, [companies]);

  return (
    <aside
      className="hidden w-72 shrink-0 flex-col overflow-y-auto lg:flex"
      style={{
        background: COLORS.panel,
        borderLeft: `1px solid ${COLORS.border}`,
        maxHeight: "calc(100vh - 100px)",
      }}
    >
      {/* Utilities strip */}
      <div className="flex items-center gap-1 px-2 py-1.5" style={{ borderBottom: `1px solid ${COLORS.border}` }}>
        <IconBtn label="Watchlist"><Icon name="bookmark" size={14} /></IconBtn>
        <IconBtn label="Clock"><Icon name="clock" size={14} /></IconBtn>
        <IconBtn label="Layers"><Icon name="layers" size={14} /></IconBtn>
      </div>

      {/* Watchlist (previously behind a tab guard; the sibling tabs were removed) */}
      <div className="flex-1">
          <div className="flex items-center justify-between px-3 py-2" style={{ borderBottom: `1px solid ${COLORS.border}` }}>
            <button className="flex items-center gap-1 text-xs font-semibold" style={{ color: COLORS.text }}>
              Watchlist <Icon name="chevron-down" size={10} />
            </button>
            <div className="flex items-center gap-1">
              <IconBtn label="Add"><Icon name="plus" size={14} /></IconBtn>
              <IconBtn label="More"><Icon name="more-vertical" size={14} /></IconBtn>
            </div>
          </div>

          {/* Column headers */}
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-3 px-3 py-1 text-[10px] font-semibold uppercase tracking-wider" style={{ color: COLORS.hint, borderBottom: `1px solid ${COLORS.border}` }}>
            <span>Symbol</span><span className="text-right">Last</span><span className="text-right">Chg</span><span className="text-right">Chg%</span>
          </div>

          {/* Format helper for the Last column: 4200.15 stays two-decimal
              formatted, 100+ two decimals, small-cap 3 decimals. */}
          {(() => {
            const fmtLast = (v: number | null | undefined) => {
              if (v == null) return "—";
              if (v >= 1000) return v.toLocaleString("en-KE", { maximumFractionDigits: 2 });
              return v.toFixed(v >= 100 ? 2 : 3);
            };
            return (
              <>
                {/* ── NSE INDICES ─────────────────────────────────────── */}
                <div>
                  <div className="flex items-center gap-1 px-3 py-1.5 text-[10px] font-semibold" style={{ color: COLORS.hint }}>
                    <Icon name="chevron-down" size={10} /> NSE INDICES
                  </div>
                  {KENYA_INDEX_KEYS.map((idx) => {
                    const reading = indexReadings?.[idx.key];
                    const chg = reading?.change_points ?? null;
                    const chgPct = reading?.change_pct ?? null;
                    const chgColor = chg == null
                      ? COLORS.hint
                      : chg >= 0 ? COLORS.buy : COLORS.sell;
                    return (
                      <Link
                        key={idx.key}
                        to="/"
                        className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-3 py-1.5 text-xs hover:bg-slate-50"
                        style={{ color: COLORS.text }}
                        title={`${idx.label} · from market_overview`}
                      >
                        <span className="flex items-center gap-2">
                          <span
                            className="flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold text-white"
                            style={{ background: idx.color }}
                          >
                            {idx.label.replace(/\s.*/, "").slice(0, 1)}
                          </span>
                          <span className="font-semibold">{idx.label}</span>
                        </span>
                        <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: COLORS.text }}>
                          {fmtLast(reading?.value)}
                        </span>
                        <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: chgColor }}>
                          {chg == null ? "—" : (chg >= 0 ? "+" : "") + chg.toFixed(2)}
                        </span>
                        <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: chgColor }}>
                          {chgPct == null ? "—" : (chgPct >= 0 ? "+" : "") + chgPct.toFixed(2) + "%"}
                        </span>
                      </Link>
                    );
                  })}
                </div>

                {/* ── NSE STOCKS ──────────────────────────────────────── */}
                <div>
                  <div className="flex items-center gap-1 px-3 py-1.5 text-[10px] font-semibold" style={{ color: COLORS.hint }}>
                    <Icon name="chevron-down" size={10} /> NSE STOCKS
                  </div>
                  {stockRows.length === 0 ? (
                    <p className="px-3 py-2 text-[10px] italic" style={{ color: COLORS.hint }}>
                      Loading NSE tickers…
                    </p>
                  ) : (
                    stockRows.map((c) => {
                      const price = c.current_price ?? c.last_known_price ?? null;
                      const chgPct = c.change_pct_today ?? null;
                      const chgAbs =
                        price != null && chgPct != null && chgPct !== 0
                          ? (price / (1 + chgPct / 100)) * (chgPct / 100)
                          : null;
                      const chgColor = chgPct == null
                        ? COLORS.hint
                        : chgPct >= 0 ? COLORS.buy : COLORS.sell;
                      return (
                        <Link
                          key={c.id}
                          to={`/chart/${c.ticker}`}
                          className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-3 py-1.5 text-xs hover:bg-slate-50"
                          style={{ color: COLORS.text }}
                          title={c.name}
                        >
                          <span className="flex items-center gap-2">
                            <span
                              className="flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold text-white"
                              style={{ background: c.color || COLORS.accent }}
                            >
                              {c.short.slice(0, 1)}
                            </span>
                            <span className="font-semibold">{c.short}</span>
                          </span>
                          <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: COLORS.text }}>
                            {fmtLast(price)}
                          </span>
                          <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: chgColor }}>
                            {chgAbs == null ? "—" : (chgAbs >= 0 ? "+" : "") + chgAbs.toFixed(2)}
                          </span>
                          <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: chgColor }}>
                            {chgPct == null ? "—" : (chgPct >= 0 ? "+" : "") + chgPct.toFixed(2) + "%"}
                          </span>
                        </Link>
                      );
                    })
                  )}
                </div>
              </>
            );
          })()}
          <p className="px-3 py-2 text-[10px] italic" style={{ color: COLORS.hint }}>
            Live NSE indices + NSE tickers. Click any row to jump into its chart.
          </p>
        </div>

      {/* Company deep-dive card at the bottom */}
      {company && (
        <div className="flex flex-col gap-2 border-t px-3 py-3" style={{ borderColor: COLORS.border }}>
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <span
                className="flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold text-white"
                style={{ background: company.color || COLORS.accent }}
              >
                {company.short?.slice(0, 1)}
              </span>
              <span className="text-xs font-bold" style={{ color: COLORS.text }}>{company.short}</span>
            </span>
            <div className="flex items-center gap-1">
              <IconBtn label="Detail"><Icon name="grid" size={12} /></IconBtn>
              <IconBtn label="Edit"><Icon name="edit" size={12} /></IconBtn>
              <IconBtn label="More"><Icon name="more-vertical" size={12} /></IconBtn>
            </div>
          </div>
          <a
            href={`/company/${company.id}`}
            className="text-[11px] hover:underline"
            style={{ color: COLORS.text }}
          >
            {company.name} <Icon name="external" size={10} />
          </a>
          <p className="text-[10px]" style={{ color: COLORS.hint }}>
            {company.sector || "—"}
          </p>
          <div className="flex items-baseline gap-2 pt-1">
            <span className="text-2xl font-bold font-mono tabular-nums" style={{ color: COLORS.text }}>
              {latestPrice != null ? latestPrice.toFixed(2) : "—"}
            </span>
            <span className="text-[10px] font-semibold" style={{ color: COLORS.hint }}>KES</span>
            {changeAbs != null && (
              <span className="font-mono text-xs tabular-nums" style={{ color: changeColor }}>
                {changeAbs >= 0 ? "+" : ""}{changeAbs.toFixed(2)}
              </span>
            )}
            {changePct != null && (
              <span className="font-mono text-xs tabular-nums" style={{ color: changeColor }}>
                {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 text-[10px]" style={{ color: COLORS.buy }}>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: COLORS.buy }} />
            <span>Market open</span>
          </div>

          {/* Key stats grid */}
          <div className="mt-2 grid grid-cols-2 gap-y-1.5 text-[11px]">
            <span style={{ color: COLORS.muted }}>Volume</span>
            <span className="text-right font-mono tabular-nums" style={{ color: COLORS.text }}>
              {company.volume_today != null ? fmtCompact(company.volume_today) : "—"}
            </span>
            <span style={{ color: COLORS.muted }}>Period high</span>
            <span className="text-right font-mono tabular-nums" style={{ color: COLORS.text }}>
              {periodMax > 0 ? periodMax.toFixed(2) : "—"}
            </span>
            <span style={{ color: COLORS.muted }}>Period low</span>
            <span className="text-right font-mono tabular-nums" style={{ color: COLORS.text }}>
              {periodMin > 0 ? periodMin.toFixed(2) : "—"}
            </span>
            <span style={{ color: COLORS.muted }}>Price date</span>
            <span className="text-right font-mono tabular-nums" style={{ color: COLORS.text }}>
              {company.price_date || "—"}
            </span>
            <span style={{ color: COLORS.muted }}>Signal</span>
            <span className="text-right font-mono tabular-nums" style={{ color: company.signal === "BUY" ? COLORS.buy : company.signal === "SELL" ? COLORS.sell : COLORS.muted }}>
              {company.signal || "—"}
            </span>
          </div>
        </div>
      )}
    </aside>
  );
};

// ─── Alert modal ────────────────────────────────────────────────────────────

const AlertModal: FC<{
  symbol: string;
  currentPrice: number | null;
  onClose: () => void;
  onSave: (a: Omit<PriceAlert, "id" | "created_at">) => void;
}> = ({ symbol, currentPrice, onClose, onSave }) => {
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [threshold, setThreshold] = useState<string>(
    currentPrice != null
      ? (direction === "above" ? currentPrice * 1.05 : currentPrice * 0.95).toFixed(2)
      : "",
  );
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Close on Escape key — standard modal behaviour.
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  }, [onClose]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const value = parseFloat(threshold);
    if (!Number.isFinite(value) || value <= 0) {
      setError("Threshold must be a positive number");
      return;
    }
    onSave({ threshold: value, direction, note: note.trim() || undefined });
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-lg shadow-xl"
        style={{ background: COLORS.panel, color: COLORS.text }}
      >
        <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: `1px solid ${COLORS.border}` }}>
          <div>
            <p className="text-sm font-bold">Create alert · {symbol}</p>
            {currentPrice != null && (
              <p className="text-[11px]" style={{ color: COLORS.hint }}>
                Current: KES {currentPrice.toFixed(2)}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 hover:bg-slate-100" style={{ color: COLORS.muted }}>
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider" style={{ color: COLORS.muted }}>
              Trigger when price is
            </label>
            <div className="grid grid-cols-2 gap-1 rounded-md p-0.5" style={{ background: COLORS.bg }}>
              {(["above", "below"] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDirection(d)}
                  className="rounded px-3 py-1.5 text-xs font-semibold"
                  style={{
                    color: direction === d ? "#FFFFFF" : COLORS.text,
                    background: direction === d
                      ? (d === "above" ? COLORS.sell : COLORS.buy)
                      : "transparent",
                  }}
                >
                  {d === "above" ? "▲ Above" : "▼ Below"}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider" style={{ color: COLORS.muted }}>
              Threshold (KES)
            </label>
            <input
              type="number"
              step="0.05"
              inputMode="decimal"
              value={threshold}
              onChange={(e) => { setThreshold(e.target.value); setError(null); }}
              autoFocus
              className="w-full rounded-md px-3 py-2 text-sm outline-none"
              style={{ background: COLORS.bg, color: COLORS.text, border: `1px solid ${error ? COLORS.sell : COLORS.border}` }}
            />
            {error && (
              <p className="mt-1 text-[11px]" style={{ color: COLORS.sell }}>{error}</p>
            )}
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider" style={{ color: COLORS.muted }}>
              Note (optional)
            </label>
            <input
              type="text"
              placeholder="e.g. Take profit here"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={80}
              className="w-full rounded-md px-3 py-2 text-sm outline-none"
              style={{ background: COLORS.bg, color: COLORS.text, border: `1px solid ${COLORS.border}` }}
            />
          </div>

          <p className="text-[10px] italic" style={{ color: COLORS.hint }}>
            Alerts are stored locally in this browser. Email / push notifications
            when the price actually crosses the threshold are a separate track
            (Firebase Function) — for now the alert only shows as a line on the chart.
          </p>
        </div>

        <div className="flex items-center justify-end gap-2 px-5 py-3" style={{ borderTop: `1px solid ${COLORS.border}` }}>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-3 py-1.5 text-xs font-semibold hover:bg-slate-100"
            style={{ color: COLORS.text }}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="rounded px-4 py-1.5 text-xs font-bold text-white"
            style={{ background: COLORS.accent }}
          >
            Create alert
          </button>
        </div>
      </form>
    </div>
  );
};

// ─── Bottom timeframe strip ─────────────────────────────────────────────────

const BottomTimeframeStrip: FC<{
  range: RangeKey;
  onChange: (r: RangeKey) => void;
  customRange: { start: string; end: string };
  onCustomRangeChange: (r: { start: string; end: string }) => void;
}> = ({ range, onChange, customRange, onCustomRangeChange }) => (
  <div
    className="flex flex-wrap items-center gap-1 overflow-x-auto whitespace-nowrap px-2 py-1 sm:px-3 sm:py-1.5"
    style={{ borderTop: `1px solid ${COLORS.border}`, background: COLORS.panel }}
  >
    {RANGES.map((r) => (
      <button
        key={r.key}
        type="button"
        onClick={() => onChange(r.key)}
        className="rounded px-2 py-1 text-[11px] font-semibold sm:py-0.5"
        style={{
          color: r.key === range ? COLORS.accent : COLORS.muted,
          background: r.key === range ? COLORS.bg : "transparent",
        }}
      >
        {r.key}
      </button>
    ))}
    {range === "Custom" && (
      <div className="ml-2 flex items-center gap-1 text-[11px]" style={{ color: COLORS.muted }}>
        <span>from</span>
        <input
          type="date"
          value={customRange.start}
          max={customRange.end}
          onChange={(e) => onCustomRangeChange({ ...customRange, start: e.target.value })}
          className="rounded border px-1 py-0.5 font-mono text-[11px] outline-none"
          style={{ background: COLORS.bg, borderColor: COLORS.border, color: COLORS.text }}
        />
        <span>to</span>
        <input
          type="date"
          value={customRange.end}
          min={customRange.start}
          onChange={(e) => onCustomRangeChange({ ...customRange, end: e.target.value })}
          className="rounded border px-1 py-0.5 font-mono text-[11px] outline-none"
          style={{ background: COLORS.bg, borderColor: COLORS.border, color: COLORS.text }}
        />
      </div>
    )}
    <span className="ml-3 hidden text-[10px] sm:inline" style={{ color: COLORS.hint }}>
      UTC · adjusted
    </span>
  </div>
);

// ─── Icon library ───────────────────────────────────────────────────────────
// Minimal SVG set — enough for the workstation without pulling in an icon
// library. Names mirror TradingView / Lucide conventions so they're easy to
// substitute later.

const IconBtn: FC<{
  label: string;
  children: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  active?: boolean;
  disabled?: boolean;
}> = ({ label, children, onClick, active, disabled }) => (
  <button
    type="button"
    title={label}
    aria-label={label}
    onClick={onClick}
    disabled={disabled}
    className="flex h-7 w-7 items-center justify-center rounded hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
    style={{
      color: active ? COLORS.accent : COLORS.muted,
      background: active ? COLORS.bg : "transparent",
    }}
  >
    {children}
  </button>
);

const TextBtn: FC<{
  icon?: string;
  children: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
}> = ({ icon, children, onClick, active, disabled, title }) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    title={title}
    className="flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
    style={{
      color: active ? COLORS.accent : COLORS.text,
      background: active ? COLORS.bg : "transparent",
    }}
  >
    {icon && <Icon name={icon} size={14} />}
    <span>{children}</span>
  </button>
);

const Icon: FC<{ name: string; size?: number }> = ({ name, size = 16 }) => {
  const s = size;
  const stroke = "currentColor";
  const common = { width: s, height: s, viewBox: "0 0 24 24", fill: "none", stroke, strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "menu":         return <svg {...common}><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>;
    case "chevron-down": return <svg {...common}><polyline points="6 9 12 15 18 9"/></svg>;
    case "chevron-left": return <svg {...common}><polyline points="15 18 9 12 15 6"/></svg>;
    case "chevron-right":return <svg {...common}><polyline points="9 18 15 12 9 6"/></svg>;
    case "plus":         return <svg {...common}><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>;
    case "plus-circle":  return <svg {...common}><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>;
    case "line-chart":   return <svg {...common}><polyline points="3 17 9 11 13 15 21 7"/></svg>;
    case "area-chart":   return <svg {...common}><polyline points="3 17 9 11 13 15 21 7"/><polyline points="3 21 21 21"/></svg>;
    case "grid":         return <svg {...common}><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>;
    case "layers":       return <svg {...common}><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>;
    case "bell":         return <svg {...common}><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>;
    case "rewind":       return <svg {...common}><polygon points="11 19 2 12 11 5 11 19"/><polygon points="22 19 13 12 22 5 22 19"/></svg>;
    case "undo":         return <svg {...common}><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/></svg>;
    case "redo":         return <svg {...common}><path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 15-6.7L21 13"/></svg>;
    case "layout":       return <svg {...common}><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/></svg>;
    case "save":         return <svg {...common}><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/></svg>;
    case "briefcase":    return <svg {...common}><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>;
    case "maximize":     return <svg {...common}><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>;
    case "minimize":     return <svg {...common}><path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/></svg>;
    case "bar-chart":    return <svg {...common}><line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/></svg>;
    case "camera":       return <svg {...common}><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>;
    case "bookmark":     return <svg {...common}><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>;
    case "clock":        return <svg {...common}><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>;
    case "edit":         return <svg {...common}><path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z"/></svg>;
    case "more-vertical":return <svg {...common}><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>;
    case "external":     return <svg {...common}><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>;
    case "crosshair":    return <svg {...common}><circle cx="12" cy="12" r="10"/><line x1="22" y1="12" x2="18" y2="12"/><line x1="6" y1="12" x2="2" y2="12"/><line x1="12" y1="6" x2="12" y2="2"/><line x1="12" y1="22" x2="12" y2="18"/></svg>;
    case "trend-line":   return <svg {...common}><line x1="4" y1="20" x2="20" y2="4"/><circle cx="4" cy="20" r="2"/><circle cx="20" cy="4" r="2"/></svg>;
    case "channel":      return <svg {...common}><line x1="4" y1="18" x2="20" y2="6"/><line x1="4" y1="14" x2="20" y2="2"/></svg>;
    case "fib":          return <svg {...common}><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/><line x1="3" y1="14" x2="21" y2="14"/><line x1="3" y1="18" x2="21" y2="18"/></svg>;
    case "brush":        return <svg {...common}><path d="M12 19c-1 0-3-1-3-4s2-4 3-4 3 1 3 4-2 4-3 4z"/><path d="M14 12l6-6a2 2 0 0 0-3-3l-6 6"/></svg>;
    case "text":         return <svg {...common}><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg>;
    case "pattern":      return <svg {...common}><polygon points="12 2 22 8 22 16 12 22 2 16 2 8 12 2"/></svg>;
    case "ruler":        return <svg {...common}><path d="M2 15l6-6 6 6-6 6z"/><path d="M14 3l7 7-2 2-7-7z"/></svg>;
    case "zoom":         return <svg {...common}><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>;
    case "magnet":       return <svg {...common}><path d="M6 3v9a6 6 0 0 0 12 0V3"/><line x1="6" y1="3" x2="10" y2="3"/><line x1="14" y1="3" x2="18" y2="3"/></svg>;
    case "lock":         return <svg {...common}><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>;
    case "eye-off":      return <svg {...common}><path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a19.61 19.61 0 0 1 4.22-5.94"/><line x1="1" y1="1" x2="23" y2="23"/></svg>;
    case "trash":        return <svg {...common}><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/></svg>;
    case "x":            return <svg {...common}><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>;
    default:             return <svg {...common}><circle cx="12" cy="12" r="10"/></svg>;
  }
};
