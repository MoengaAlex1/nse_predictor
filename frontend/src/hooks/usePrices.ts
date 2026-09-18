import { useMemo } from "react";
import { useHistoricalPrices, type RtdbPricePoint } from "./useHistoricalPrices";
import type { PricePoint } from "../types";

export interface UsePricesResult {
  /** RTDB rows sorted ascending, with the decimal-scale guard applied. Feeds
   *  every downstream consumer — OHLCV panels, headers, chart, news overlay. */
  rows: RtdbPricePoint[];
  /** Chart-ready PricePoint[] derived from `rows` (date + close). */
  points: PricePoint[];
  /** Last surviving row after the guard. Feeds price headers, banners, and
   *  the MarketQuotePanel. If the current session's raw row was dropped,
   *  this is the previous good session — matching what the chart shows. */
  latest: RtdbPricePoint | null;
  /** Untouched RTDB rows (pre-guard, unsorted as returned by Firebase).
   *  Use ONLY when a consumer genuinely needs the raw stream — e.g. an
   *  audit view. Regular UI should stick to `rows`/`points`/`latest`. */
  rawRows: RtdbPricePoint[];
  /** Number of rows the decimal-scale guard dropped this render. */
  droppedCount: number;
  isLoading: boolean;
  isError: boolean;
}

/**
 * Single canonical read path for RTDB `prices/{TICKER}/{date}`.
 *
 * Applies the OCR decimal-scale guard once, here, so every page (Chart,
 * Header, Banner, Quote panel, News overlay) sees the same series. A row
 * whose close is ≥50% off both its stored `pc` AND the previous rendered
 * close is a power-of-ten shift, not a real move (NSE band is ±10%),
 * and is dropped — same rule that used to live inline in CompanyDeepDive.
 *
 * The hook is deliberately thin around `useHistoricalPrices` so callers
 * can still peek at `rawRows` when they need to (audit UI), but nothing
 * user-facing should reach past `rows`/`points`/`latest` — that's the
 * single-channel contract.
 */
export function usePrices(
  safeTicker: string,
  startDate: string,
  endDate: string,
): UsePricesResult {
  const query = useHistoricalPrices(safeTicker, startDate, endDate);
  // TanStack Query returns a referentially stable `data` array while the
  // cache entry hasn't changed, so keying the memo on `query.data` (rather
  // than a destructured `rawRows = query.data ?? []`) means we only rebuild
  // when the underlying data actually turned over.
  const queryData = query.data;

  const { rows, points, latest, droppedCount, rawRows } = useMemo(() => {
    const raw = queryData ?? [];
    const sorted = [...raw].sort((a, b) => a.date.localeCompare(b.date));
    const kept: RtdbPricePoint[] = [];
    const chart: PricePoint[] = [];
    let lastGood: number | null = null;
    let dropped = 0;

    for (const row of sorted) {
      const c = row.c;
      if (c === null || c === undefined || c <= 0) continue;
      const pc = row.pc;
      const anchor = typeof pc === "number" && pc > 0 ? pc : lastGood;
      if (anchor !== null && anchor > 0) {
        const ratio = c / anchor;
        if (ratio < 0.5 || ratio > 2.0) {
          dropped += 1;
          if (typeof console !== "undefined") {
            // eslint-disable-next-line no-console
            console.warn(
              `[usePrices] Dropping ${safeTicker} ${row.date}: close=${c} vs anchor=${anchor} — decimal-scale error`,
            );
          }
          continue;
        }
      }
      kept.push(row);
      chart.push({ date: row.date, price: c });
      lastGood = c;
    }

    return {
      rows: kept,
      points: chart,
      latest: kept.length > 0 ? kept[kept.length - 1] : null,
      droppedCount: dropped,
      rawRows: raw,
    };
  }, [queryData, safeTicker]);

  return {
    rows,
    points,
    latest,
    rawRows,
    droppedCount,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}
