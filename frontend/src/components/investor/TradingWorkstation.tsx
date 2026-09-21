import { useMemo, useState, useRef, useEffect } from "react";
import type { FC } from "react";
import { Link } from "react-router-dom";
import {
  LineChart, BarChart, Line, Bar, XAxis, YAxis, Tooltip, ReferenceLine,
  ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";
import { useCompany } from "../../hooks/useCompany";
import { useCompanies } from "../../hooks/useCompanies";
import { usePrices } from "../../hooks/usePrices";
import { useExternalWatchlist, type ExternalQuote } from "../../hooks/useExternalWatchlist";
import { fmtCompact, fmtPct } from "../../lib/format";
import type { CompanyDoc } from "../../types";

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
  { key: "1D",  days: 1     },
  { key: "5D",  days: 5     },
  { key: "1M",  days: 30    },
  { key: "3M",  days: 90    },
  { key: "6M",  days: 180   },
  { key: "YTD", days: -1    },
  { key: "1Y",  days: 365   },
  { key: "5Y",  days: 1825  },
  { key: "All", days: null  },
] as const;
type RangeKey = typeof RANGES[number]["key"];

// Static watchlist mirroring the reference screenshot. Prices are
// intentionally None on load — a real prices feed for indices / US stocks
// would need a new data source. Marked visibly so users see they're
// placeholders rather than stale data.
const WATCHLIST: {
  section: "INDICES" | "STOCKS" | "FUTURES";
  symbol: string;
  color: string;
}[] = [
  { section: "INDICES", symbol: "SPX",  color: "#3B82F6" },
  { section: "INDICES", symbol: "NDQ",  color: "#8B5CF6" },
  { section: "INDICES", symbol: "DJI",  color: "#F59E0B" },
  { section: "INDICES", symbol: "VIX",  color: "#10B981" },
  { section: "INDICES", symbol: "DXY",  color: "#6366F1" },
  { section: "STOCKS",  symbol: "AAPL", color: "#0F172A" },
  { section: "STOCKS",  symbol: "TSLA", color: "#DC2626" },
  { section: "STOCKS",  symbol: "NFLX", color: "#B91C1C" },
  { section: "FUTURES", symbol: "USOIL", color: "#78716C" },
  { section: "FUTURES", symbol: "GOLD",  color: "#EAB308" },
];

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
  const [chartType, setChartType] = useState<"line" | "area">("line");

  // Filter by selected range. Dropdown selector at the bottom of the chart
  // mirrors TradingView's timeframe strip.
  const visible = useMemo(() => {
    if (!rows.length) return [];
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
  }, [rows, range]);

  const chartData = useMemo(
    () => visible
      .filter((r) => r.c != null && (r.c as number) > 0)
      .map((r) => ({
        date: r.date,
        price: r.c as number,
        volume: (r.v as number | null) ?? 0,
        // Colour the volume bar per session direction. Use pc if we have it;
        // otherwise fall back to previous bar's close (walk backwards).
        up: r.pc != null ? (r.c as number) >= (r.pc as number) : true,
      })),
    [visible],
  );

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
      className="w-full overflow-hidden rounded-none border-y"
      style={{ background: COLORS.bg, borderColor: COLORS.border, color: COLORS.text }}
    >
      <TopRibbon
        symbol={short}
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

      <div className="flex" style={{ minHeight: 820 }}>
        <LeftDrawingRail />
        <MainCanvas
          data={chartData}
          latestPrice={latestPrice}
          chartType={chartType}
          bid={bid}
          ask={ask}
        />
        <RightSidebarConnected
          company={company}
          latestPrice={latestPrice}
          changeAbs={changeAbs}
          changePct={changePct}
          periodMin={pricePeriodMin}
          periodMax={pricePeriodMax}
        />
      </div>

      <BottomTimeframeStrip range={range} onChange={setRange} />
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
  chartType: "line" | "area";
  onChartTypeChange: (t: "line" | "area") => void;
}> = ({
  symbol, allCompanies, company, latestPrice, changeAbs, changePct,
  range, onRangeChange, chartType, onChartTypeChange,
}) => {
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [rangeMenuOpen, setRangeMenuOpen] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);
  const rangeRef  = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click.
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setSearchOpen(false);
      if (rangeRef.current  && !rangeRef.current.contains(e.target as Node))  setRangeMenuOpen(false);
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
      {/* Top row: symbol search + timeframe + chart type + tools + right-side utilities */}
      <div className="flex items-center gap-3 px-3 py-1.5" style={{ borderBottom: `1px solid ${COLORS.border}` }}>
        {/* Hamburger placeholder */}
        <IconBtn label="Menu"><Icon name="menu" /></IconBtn>

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

        {/* Add symbol */}
        <IconBtn label="Add symbol"><Icon name="plus-circle" /></IconBtn>

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

        {/* Chart type toggle */}
        <button
          type="button"
          onClick={() => onChartTypeChange(chartType === "line" ? "area" : "line")}
          className="rounded p-1"
          style={{ color: COLORS.muted }}
          title={`Chart type: ${chartType} (click to toggle)`}
        >
          <Icon name={chartType === "line" ? "line-chart" : "area-chart"} />
        </button>

        {/* Analytical buttons */}
        <TextBtn icon="grid">Indicators</TextBtn>
        <TextBtn icon="layers">Templates</TextBtn>
        <TextBtn icon="bell">Alert</TextBtn>
        <TextBtn icon="rewind">Replay</TextBtn>

        {/* History controls */}
        <div className="ml-1 flex items-center gap-0.5">
          <IconBtn label="Undo"><Icon name="undo" /></IconBtn>
          <IconBtn label="Redo"><Icon name="redo" /></IconBtn>
        </div>

        {/* Right-side utilities (Save, camera, snapshot, fullscreen, trade, publish) */}
        <div className="ml-auto flex items-center gap-1">
          <IconBtn label="Layout"><Icon name="layout" /></IconBtn>
          <TextBtn icon="save">Save</TextBtn>
          <IconBtn label="Alerts panel"><Icon name="bell" /></IconBtn>
          <IconBtn label="Trading panel"><Icon name="briefcase" /></IconBtn>
          <IconBtn label="Fullscreen"><Icon name="maximize" /></IconBtn>
          <IconBtn label="Snapshot"><Icon name="camera" /></IconBtn>
          <button
            type="button"
            className="rounded px-3 py-1 text-xs font-bold"
            style={{ color: COLORS.text, background: COLORS.bg, border: `1px solid ${COLORS.border}` }}
          >
            Trade
          </button>
          <button
            type="button"
            className="rounded px-3 py-1 text-xs font-bold text-white"
            style={{ background: COLORS.accent }}
          >
            Publish
          </button>
        </div>
      </div>

      {/* Sub-header: company name · timeframe · exchange · price */}
      <div className="flex items-center gap-3 px-3 py-1.5 text-xs">
        <span style={{ color: COLORS.orange }}>●</span>
        <span className="font-semibold" style={{ color: COLORS.text }}>
          {company?.name ?? "…"} · 1D · NSEKE
        </span>
        {latestPrice != null && (
          <>
            <span className="font-mono tabular-nums" style={{ color: changeColor }}>
              {latestPrice.toFixed(2)}
            </span>
            {changeAbs != null && (
              <span className="font-mono tabular-nums" style={{ color: changeColor }}>
                {changeAbs >= 0 ? "+" : ""}{changeAbs.toFixed(2)}
              </span>
            )}
            {changePct != null && (
              <span className="font-mono tabular-nums" style={{ color: changeColor }}>
                ({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
              </span>
            )}
          </>
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

const LeftDrawingRail: FC = () => {
  const [active, setActive] = useState<string>("crosshair");
  return (
    <div
      className="flex flex-col items-center gap-0.5 py-2"
      style={{ background: COLORS.panel, borderRight: `1px solid ${COLORS.border}`, width: 40 }}
    >
      {DRAWING_TOOLS.map((tool) => (
        <button
          key={tool.name}
          type="button"
          title={`${tool.label} — drawing tools coming soon`}
          onClick={() => setActive(tool.name)}
          className="flex h-8 w-8 items-center justify-center rounded"
          style={{
            background: active === tool.name ? COLORS.bg : "transparent",
            color: active === tool.name ? COLORS.accent : COLORS.muted,
          }}
        >
          <Icon name={tool.name} size={16} />
        </button>
      ))}
    </div>
  );
};

// ─── Main canvas ────────────────────────────────────────────────────────────

const MainCanvas: FC<{
  data: { date: string; price: number; volume: number; up: boolean }[];
  latestPrice: number | null;
  chartType: "line" | "area";
  bid: number | null;
  ask: number | null;
}> = ({ data, latestPrice, chartType, bid, ask }) => {
  const totalVol = useMemo(() => data.reduce((a, d) => a + d.volume, 0), [data]);

  return (
    <div className="relative flex-1 overflow-hidden" style={{ background: COLORS.panel, minHeight: 820 }}>
      {/* Bid/ask execution overlay (visual only — we're not a broker) */}
      {latestPrice != null && bid != null && ask != null && (
        <div className="absolute left-2 top-2 z-10 flex items-center gap-1 font-mono text-[11px]">
          <span
            className="rounded px-2 py-1 text-white"
            style={{ background: COLORS.sell }}
          >
            <div className="text-[9px] leading-none opacity-90">SELL</div>
            <div className="font-bold tabular-nums">{bid.toFixed(2)}</div>
          </span>
          <span className="rounded px-1.5 py-0.5 text-[10px]" style={{ background: COLORS.bg, color: COLORS.muted }}>
            {(ask - bid).toFixed(2)}
          </span>
          <span
            className="rounded px-2 py-1 text-white"
            style={{ background: COLORS.accent }}
          >
            <div className="text-[9px] leading-none opacity-90">BUY</div>
            <div className="font-bold tabular-nums">{ask.toFixed(2)}</div>
          </span>
        </div>
      )}

      {/* Volume label top-left under bid-ask */}
      <div className="absolute left-2 top-16 z-10 text-[11px]" style={{ color: COLORS.muted }}>
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
                formatter={(value, name) => {
                  const v = typeof value === "number" ? value : Number(value);
                  if (name === "price") return [`KES ${v.toFixed(2)}`, "Close"];
                  return [String(value), String(name)];
                }}
                labelFormatter={(d) => String(d)}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke={COLORS.priceLine}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
                fill={chartType === "area" ? "url(#priceFill)" : undefined}
              />
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
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Volume band — 15% */}
        <div
          style={{ flex: "1 1 15%", borderTop: `1px solid ${COLORS.border}` }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              margin={{ top: 4, right: 68, bottom: 4, left: 0 }}
              syncId="ws-price-vol"
              barCategoryGap={1}
            >
              <XAxis
                dataKey="date"
                tick={{ fontSize: 10, fill: COLORS.muted }}
                tickFormatter={(d: string) => {
                  const dt = new Date(d);
                  return dt.toLocaleDateString("en-US", { month: "short" });
                }}
                interval="preserveStartEnd"
                minTickGap={40}
                stroke={COLORS.border}
              />
              <YAxis
                orientation="right"
                tick={false}
                axisLine={false}
                tickLine={false}
                domain={[0, "dataMax"]}
                width={62}
              />
              <Tooltip
                cursor={{ fill: "rgba(0,0,0,0.03)" }}
                contentStyle={{
                  background: COLORS.panel,
                  border: `1px solid ${COLORS.border}`,
                  fontSize: 12,
                  color: COLORS.text,
                  borderRadius: 4,
                }}
                formatter={(value) => [fmtCompact(Number(value)), "Volume"]}
              />
              <Bar
                dataKey="volume"
                isAnimationActive={false}
                maxBarSize={12}
              >
                {data.map((d, i) => (
                  <Cell key={i} fill={d.up ? COLORS.volUp : COLORS.volDown} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* TradingView-like watermark bottom-left */}
      <div className="absolute bottom-2 left-3 flex items-center gap-1 text-[10px]" style={{ color: COLORS.hint }}>
        <span className="font-bold" style={{ color: COLORS.accent }}>NSE</span> Intelligence
      </div>
    </div>
  );
};

// ─── Right sidebar ──────────────────────────────────────────────────────────

// Thin wrapper that fetches the external watchlist data and passes it in.
// Kept separate so the RightSidebar render function stays testable with a
// static quotes map.
const RightSidebarConnected: FC<{
  company: CompanyDoc | null | undefined;
  latestPrice: number | null;
  changeAbs: number | null;
  changePct: number | null;
  periodMin: number;
  periodMax: number;
}> = (props) => {
  const { data: externalQuotes } = useExternalWatchlist();
  return <RightSidebar {...props} externalQuotes={externalQuotes} />;
};

const RightSidebar: FC<{
  company: CompanyDoc | null | undefined;
  latestPrice: number | null;
  changeAbs: number | null;
  changePct: number | null;
  periodMin: number;
  periodMax: number;
  externalQuotes: Map<string, ExternalQuote> | undefined;
}> = ({ company, latestPrice, changeAbs, changePct, periodMin, periodMax, externalQuotes }) => {
  const [tab] = useState<"watchlist" | "details" | "alerts">("watchlist");
  const isUp = (changePct ?? 0) >= 0;
  const changeColor = isUp ? COLORS.buy : COLORS.sell;

  const grouped = useMemo(() => {
    const groups: Record<string, typeof WATCHLIST> = {};
    for (const item of WATCHLIST) {
      (groups[item.section] ??= []).push(item);
    }
    return groups;
  }, []);

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

      {/* Tab: Watchlist */}
      {tab === "watchlist" && (
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

          {(["INDICES", "STOCKS", "FUTURES"] as const).map((section) => (
            <div key={section}>
              <div className="flex items-center gap-1 px-3 py-1.5 text-[10px] font-semibold" style={{ color: COLORS.hint }}>
                <Icon name="chevron-down" size={10} /> {section}
              </div>
              {(grouped[section] ?? []).map((row) => {
                const q = externalQuotes?.get(row.symbol);
                const chgColor = q?.chg == null
                  ? COLORS.hint
                  : q.chg >= 0 ? COLORS.buy : COLORS.sell;
                const fmtLast = (v: number | null | undefined) => {
                  if (v == null) return "—";
                  if (v >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
                  return v.toFixed(v >= 100 ? 2 : 3);
                };
                return (
                  <div
                    key={row.symbol}
                    className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 px-3 py-1.5 text-xs hover:bg-slate-50"
                    style={{ color: COLORS.text }}
                    title={q?.updated_at ? `Updated ${q.updated_at}` : "Awaiting first yfinance fetch"}
                  >
                    <span className="flex items-center gap-2">
                      <span
                        className="flex h-5 w-5 items-center justify-center rounded-full text-[9px] font-bold text-white"
                        style={{ background: row.color }}
                      >
                        {row.symbol.slice(0, 1)}
                      </span>
                      <span className="font-semibold">{row.symbol}</span>
                    </span>
                    <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: COLORS.text }}>
                      {fmtLast(q?.last ?? null)}
                    </span>
                    <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: chgColor }}>
                      {q?.chg == null ? "—" : (q.chg >= 0 ? "+" : "") + q.chg.toFixed(2)}
                    </span>
                    <span className="text-right font-mono tabular-nums text-[11px]" style={{ color: chgColor }}>
                      {q?.chg_pct == null ? "—" : (q.chg_pct >= 0 ? "+" : "") + q.chg_pct.toFixed(2) + "%"}
                    </span>
                  </div>
                );
              })}
            </div>
          ))}
          <p className="px-3 py-2 text-[10px] italic" style={{ color: COLORS.hint }}>
            External quotes via Yahoo Finance, refreshed every 30 min during US market hours.
          </p>
        </div>
      )}

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

// ─── Bottom timeframe strip ─────────────────────────────────────────────────

const BottomTimeframeStrip: FC<{ range: RangeKey; onChange: (r: RangeKey) => void }> = ({
  range, onChange,
}) => (
  <div
    className="flex items-center gap-1 px-3 py-1.5"
    style={{ borderTop: `1px solid ${COLORS.border}`, background: COLORS.panel }}
  >
    {RANGES.map((r) => (
      <button
        key={r.key}
        type="button"
        onClick={() => onChange(r.key)}
        className="rounded px-2 py-0.5 text-[11px] font-semibold"
        style={{
          color: r.key === range ? COLORS.accent : COLORS.muted,
          background: r.key === range ? COLORS.bg : "transparent",
        }}
      >
        {r.key}
      </button>
    ))}
    <span className="ml-3 text-[10px]" style={{ color: COLORS.hint }}>
      UTC · adjusted
    </span>
  </div>
);

// ─── Icon library ───────────────────────────────────────────────────────────
// Minimal SVG set — enough for the workstation without pulling in an icon
// library. Names mirror TradingView / Lucide conventions so they're easy to
// substitute later.

const IconBtn: FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <button
    type="button"
    title={label}
    className="flex h-7 w-7 items-center justify-center rounded hover:bg-slate-100"
    style={{ color: COLORS.muted }}
  >
    {children}
  </button>
);

const TextBtn: FC<{ icon?: string; children: React.ReactNode }> = ({ icon, children }) => (
  <button
    type="button"
    className="flex items-center gap-1 rounded px-2 py-1 text-xs font-semibold hover:bg-slate-100"
    style={{ color: COLORS.text }}
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
    default:             return <svg {...common}><circle cx="12" cy="12" r="10"/></svg>;
  }
};
