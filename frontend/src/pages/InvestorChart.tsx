import { useEffect, useMemo, useState, useCallback } from "react";
import { useParams, Link, useSearchParams } from "react-router-dom";
import { useRecentTickers } from "../hooks/useRecentTickers";
import { useCompany, useLatestTechnicals, useFinancials as useFinancialsDoc } from "../hooks/useCompany";
import { useCompanies } from "../hooks/useCompanies";
import { useHistoricalPrices } from "../hooks/useHistoricalPrices";
import { useCompareSeries } from "../hooks/useCompareSeries";
import { useWatchlist } from "../hooks/useWatchlist";
import { usePeers } from "../hooks/usePeers";
import { CompanyLogo } from "../components/ui/CompanyLogo";
import { LeftWatchlistRail } from "../components/layout/LeftWatchlistRail";
import { TimeframeTabs } from "../components/ui/TimeframeTabs";
import { FocusedPriceChart } from "../components/investor/FocusedPriceChart";
import { CompareChart, type CompareLine } from "../components/investor/CompareChart";
import { CompareControls } from "../components/investor/CompareControls";
import { FilingsPanel } from "../components/investor/FilingsPanel";
import {
  cleanTicker,
  FETCH_START,
  todayIso,
  type TimeframeKey,
} from "../lib/timeframe";
import {
  fmtKes,
  fmtChangeSigned,
  fmtPct,
  fmtCompact,
  arrow,
  trendClass,
  EM_DASH,
} from "../lib/format";
import type { RtdbPricePoint } from "../hooks/useHistoricalPrices";

const StarIcon = ({ filled }: { filled?: boolean }) => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
  </svg>
);

const ExtLinkIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <polyline points="15 3 21 3 21 9" />
    <line x1="10" y1="14" x2="21" y2="3" />
  </svg>
);

// Compare-mode palette. Five hues spaced ~70° apart on the wheel so any
// three consecutive lines stay visually distinct on both dark and light
// canvases. Primary gets index 0 in compare mode (overriding the brand
// colour that may accidentally collide with a compare hue); comparisons
// get 1..4. Avoids pure green/red so the "up/down" colour semantics
// stay reserved for delta indicators.
const COMPARE_PALETTE = [
  "#3b82f6", // blue-500   — primary in compare mode
  "#f97316", // orange-500
  "#a855f7", // purple-500
  "#eab308", // yellow-500
  "#14b8a6", // teal-500
];
const MAX_COMPARE = 4;

function filterByTimeframeRtdb(points: RtdbPricePoint[], tf: TimeframeKey): RtdbPricePoint[] {
  if (!points.length) return points;
  if (tf === "Max") return points;
  if (tf === "YTD") {
    const cut = `${new Date().getFullYear()}-01-01`;
    return points.filter((p) => p.date >= cut);
  }
  const daysMap: Record<TimeframeKey, number> = {
    "1D": 1,
    "5D": 5,
    "1M": 30,
    "3M": 90,
    YTD: 0,
    "1Y": 365,
    "3Y": 1095,
    "5Y": 1825,
    Max: 0,
  };
  const days = daysMap[tf];
  if (tf === "1D") return points.slice(-1);
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  const iso = cutoff.toISOString().slice(0, 10);
  return points.filter((p) => p.date >= iso);
}

function parseCompareParam(raw: string | null, primary: string): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter((t) => t.length > 0 && t !== primary.toUpperCase())
    .filter((t, i, arr) => arr.indexOf(t) === i)
    .slice(0, MAX_COMPARE);
}

export const InvestorChart = () => {
  const { ticker: rawTicker = "" } = useParams<{ ticker: string }>();
  const ticker = rawTicker.toUpperCase();
  const cleaned = cleanTicker(ticker);
  const pushRecent = useRecentTickers((s) => s.push);

  const [searchParams, setSearchParams] = useSearchParams();
  const compareTickers = useMemo(
    () => parseCompareParam(searchParams.get("compare"), ticker),
    [searchParams, ticker],
  );

  const [timeframe, setTimeframe] = useState<TimeframeKey>("1M");
  const [chartType, setChartType] = useState<"area" | "candles" | "indicators">("area");

  useEffect(() => {
    if (ticker) pushRecent(ticker);
  }, [ticker, pushRecent]);

  // Some entry points send us the display ticker (SCOM.NR), others send
  // the doc id (SCOM). Normalise once and use the cleaned form for every
  // Firestore + RTDB fetch — the doc id is the canonical key.
  const { data: company } = useCompany(cleaned);
  const { data: technicals } = useLatestTechnicals(cleaned);
  const { data: financials } = useFinancialsDoc(cleaned);
  const { data: allCompanies = [] } = useCompanies();
  const { data: rtdbPrimary = [] } = useHistoricalPrices(cleaned, FETCH_START, todayIso());
  const compareResults = useCompareSeries(compareTickers, FETCH_START, todayIso());
  const peers = usePeers(ticker, company?.sector ?? null, 6);

  const visiblePrimary = useMemo(
    () => filterByTimeframeRtdb(rtdbPrimary, timeframe),
    [rtdbPrimary, timeframe],
  );

  const latestRow = rtdbPrimary.length > 0 ? rtdbPrimary[rtdbPrimary.length - 1] : null;
  const previousClose = latestRow?.pc ?? null;
  const currentPrice = company?.current_price ?? latestRow?.c ?? null;
  const changePct = company?.change_pct_today ?? latestRow?.pch ?? null;
  const changeAbs =
    currentPrice != null && previousClose != null ? currentPrice - previousClose : null;
  const up = changePct != null && changePct >= 0;
  const trendColor = trendClass(changePct);

  const { isAuthenticated, has, add, remove, isPending } = useWatchlist();
  const isWatched = has(ticker);

  const canonical = allCompanies.find((c) => c.ticker.toUpperCase() === ticker);
  const displayName = company?.name ?? canonical?.name ?? ticker;
  const displaySector = company?.sector ?? canonical?.sector ?? null;
  const brandColor = company?.color ?? canonical?.color ?? "rgb(var(--accent))";
  const primaryShort = company?.short ?? canonical?.short ?? ticker;

  const inCompareMode = compareTickers.length > 0;

  // In compare mode, override the brand colour with the palette's first
  // slot so the primary line stays distinct from every compare line —
  // otherwise a Firestore brand colour could collide with a palette hue
  // and the two lines would be hard to tell apart. Solo mode keeps
  // company.color so brand identity survives on the single-line view.
  const primaryLineColor = inCompareMode ? COMPARE_PALETTE[0] : brandColor;

  // Compare-mode metadata: per-ticker short + color + today's Δ, keyed by
  // ticker so CompareControls chips can render coloured swatches + deltas
  // without re-doing the lookup. Compare tickers get palette slots 1..4
  // (0 is reserved for the primary).
  const compareMeta = useMemo(() => {
    const m = new Map<string, { short: string; color: string; changePct: number | null }>();
    compareTickers.forEach((t, i) => {
      const meta = allCompanies.find((c) => c.ticker.toUpperCase() === t);
      m.set(t, {
        short: meta?.short ?? t,
        color: COMPARE_PALETTE[(i + 1) % COMPARE_PALETTE.length],
        changePct: meta?.change_pct_today ?? null,
      });
    });
    return m;
  }, [compareTickers, allCompanies]);

  // Build the CompareChart series list — primary first, then comparisons
  // in the same order they appear in the URL param.
  const compareLines: CompareLine[] = useMemo(() => {
    if (!inCompareMode) return [];
    const primaryLine: CompareLine = {
      ticker: ticker,
      short: primaryShort,
      color: primaryLineColor,
      points: visiblePrimary
        .filter((p) => p.c != null)
        .map((p) => ({ date: p.date, price: p.c as number })),
    };
    const compareLinesArr = compareResults.map((r, i) => {
      const meta = compareMeta.get(r.ticker) ?? {
        short: r.ticker,
        color: COMPARE_PALETTE[(i + 1) % COMPARE_PALETTE.length],
        changePct: null,
      };
      return {
        ticker: r.ticker,
        short: meta.short,
        color: meta.color,
        points: filterByTimeframeRtdb(r.points, timeframe)
          .filter((p) => p.c != null)
          .map((p) => ({ date: p.date, price: p.c as number })),
      };
    });
    return [primaryLine, ...compareLinesArr];
  }, [inCompareMode, ticker, primaryShort, primaryLineColor, visiblePrimary, compareResults, compareMeta, timeframe]);

  const setCompareParam = useCallback(
    (next: string[]) => {
      const params = new URLSearchParams(searchParams);
      if (next.length === 0) params.delete("compare");
      else params.set("compare", next.join(","));
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const addCompare = useCallback(
    (t: string) => {
      const upper = t.toUpperCase();
      if (compareTickers.includes(upper) || upper === ticker) return;
      if (compareTickers.length >= MAX_COMPARE) return;
      setCompareParam([...compareTickers, upper]);
    },
    [compareTickers, ticker, setCompareParam],
  );

  const removeCompare = useCallback(
    (t: string) => {
      const upper = t.toUpperCase();
      setCompareParam(compareTickers.filter((x) => x !== upper));
    },
    [compareTickers, setCompareParam],
  );

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-4 sm:px-6 lg:px-8">
      <div className="grid gap-3 lg:grid-cols-[240px_minmax(0,1fr)]">
        <LeftWatchlistRail />

        <div className="flex flex-col gap-3">
          {/* ── Ticker header ────────────────────────────────────────────── */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rim bg-surface px-4 py-3">
            <div className="flex min-w-0 items-center gap-3">
              {company && (
                <CompanyLogo
                  id={ticker}
                  short={company.short}
                  color={company.color}
                  icon={company.icon}
                  size="lg"
                />
              )}
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <h1 className="truncate text-base font-bold text-ink">{displayName}</h1>
                  <span className="shrink-0 font-mono text-xs text-muted">({ticker})</span>
                  <Link
                    to={`/company/${ticker}`}
                    className="shrink-0 text-hint transition-colors hover:text-ink"
                    title="Open full report"
                    aria-label="Open full report"
                  >
                    <ExtLinkIcon />
                  </Link>
                </div>
                <p className="truncate text-[10px] uppercase tracking-wider text-hint">
                  Nairobi Securities Exchange
                  {displaySector && <> · {displaySector}</>}
                </p>
              </div>
              <button
                type="button"
                disabled={!isAuthenticated || isPending}
                title={
                  !isAuthenticated
                    ? "Sign in to add to watchlist"
                    : isWatched
                    ? `Remove ${ticker} from watchlist`
                    : `Add ${ticker} to watchlist`
                }
                onClick={() => (isWatched ? remove(ticker) : add(ticker))}
                className={`ml-2 flex h-7 shrink-0 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-semibold transition-colors ${
                  isAuthenticated && isWatched
                    ? "border-accent bg-accent/10 text-accent"
                    : !isAuthenticated
                    ? "cursor-not-allowed border-seam bg-raised/50 text-hint"
                    : "border-rim bg-raised text-ink hover:bg-raised/70"
                }`}
              >
                <StarIcon filled={isWatched} />
                <span>{isWatched ? "Watching" : "Watchlist"}</span>
              </button>
            </div>

            <div className="flex shrink-0 items-baseline gap-x-2 gap-y-1">
              {currentPrice != null ? (
                <>
                  <span className="font-mono text-2xl font-black text-ink tabular-nums">
                    {fmtKes(currentPrice)}
                  </span>
                  {changeAbs != null && changePct != null && (
                    <span className={`font-mono text-sm font-semibold tabular-nums ${trendColor}`}>
                      {arrow(up)} {fmtChangeSigned(changeAbs)} ({fmtPct(changePct)})
                    </span>
                  )}
                  <span className="ml-1 text-[10px] uppercase tracking-wider text-hint">
                    24H change
                  </span>
                  {(company?.price_date ?? latestRow?.date) && (
                    <span className="text-[10px] text-hint">
                      · {company?.price_date ?? latestRow?.date}
                    </span>
                  )}
                </>
              ) : (
                <span className="text-xl text-hint">{EM_DASH}</span>
              )}
            </div>
          </div>

          {/* ── Chart card ───────────────────────────────────────────────── */}
          {/* No overflow-hidden here — CompareControls' Add-dropdown pops
              down from inside this card and would be clipped otherwise.
              Recharts' ResponsiveContainer keeps the chart within bounds
              on its own, so nothing bleeds. */}
          <div className="rounded-xl border border-rim bg-surface">
            {/* Timeframe + chart-type toolbar */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-2.5">
              <TimeframeTabs value={timeframe} onChange={setTimeframe} />
              <div className="flex items-center gap-0.5 rounded-lg border border-rim bg-raised p-0.5">
                {(["area", "candles", "indicators"] as const).map((k) => {
                  const active = chartType === k;
                  const supported = k === "area";
                  return (
                    <button
                      key={k}
                      type="button"
                      disabled={!supported}
                      onClick={() => supported && setChartType(k)}
                      title={supported ? undefined : `${k[0].toUpperCase()}${k.slice(1)} — coming soon`}
                      className={`rounded-md px-2 py-1 text-[10px] font-semibold transition-colors ${
                        active && supported
                          ? "bg-accent text-white dark:bg-accent/20 dark:text-accent"
                          : supported
                          ? "text-muted hover:text-ink"
                          : "cursor-not-allowed text-hint"
                      }`}
                    >
                      {k[0].toUpperCase() + k.slice(1)}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Compare controls — primary swatch matches the chart line
                colour (brand colour in solo mode, palette[0] in compare
                mode) so the chip legend always mirrors the chart. */}
            <CompareControls
              primary={{
                ticker,
                short: primaryShort,
                color: primaryLineColor,
                changePct,
              }}
              compareTickers={compareTickers}
              compareMeta={compareMeta}
              onAdd={addCompare}
              onRemove={removeCompare}
              suggested={peers}
              maxCompare={MAX_COMPARE}
            />

            {/* Main chart — single-line + volume when solo, normalized % lines when comparing */}
            <div className="px-2 py-2">
              {inCompareMode ? (
                <CompareChart series={compareLines} height={620} />
              ) : (
                <FocusedPriceChart
                  data={visiblePrimary}
                  color={primaryLineColor}
                  height={620}
                />
              )}
              {visiblePrimary.length > 0 && financials && (
                <div className="mt-3">
                  <FilingsPanel financials={financials} />
                </div>
              )}
              {visiblePrimary.length > 0 && (
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-2 text-[10px] text-hint">
                  <span className="font-mono tabular-nums">
                    {visiblePrimary[0].date} → {visiblePrimary[visiblePrimary.length - 1].date} ·{" "}
                    {visiblePrimary.length} trading{" "}
                    {visiblePrimary.length === 1 ? "day" : "days"}
                    {inCompareMode && (
                      <span className="ml-2 text-hint">
                        · showing % change from timeframe start
                      </span>
                    )}
                  </span>
                  <span className="flex items-center gap-3">
                    {technicals?.avg_volume_30d != null && !inCompareMode && (
                      <span>
                        Avg Vol 30d:{" "}
                        <span className="font-mono tabular-nums text-muted">
                          {fmtCompact(technicals.avg_volume_30d)}
                        </span>
                      </span>
                    )}
                    <Link
                      to={`/dashboard/${ticker}`}
                      className="rounded border border-seam px-1.5 py-0.5 font-medium transition-colors hover:border-rim hover:text-ink"
                    >
                      Overview →
                    </Link>
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
