import type { PricePoint } from "../types";

export type TimeframeKey = "1D" | "5D" | "1M" | "3M" | "YTD" | "1Y" | "3Y" | "5Y" | "Max";

export const TIMEFRAMES: TimeframeKey[] = ["1D", "5D", "1M", "3M", "YTD", "1Y", "3Y", "5Y", "Max"];

const DAYS: Record<TimeframeKey, number | "ytd" | null> = {
  "1D": 1,
  "5D": 5,
  "1M": 30,
  "3M": 90,
  YTD: "ytd",
  "1Y": 365,
  "3Y": 1095,
  "5Y": 1825,
  Max: null,
};

// NSE has no intraday tick feed today, so 1D falls back to the most recent
// EOD snapshot rendered as a single point / flat line. Consumers should also
// surface the "EOD only" chip so users understand the constraint.
export const NO_INTRADAY = true;

export function filterByTimeframe(points: PricePoint[], tf: TimeframeKey): PricePoint[] {
  if (!points.length) return points;
  const rule = DAYS[tf];
  if (rule === null) return points;
  if (rule === "ytd") {
    const yearStart = `${new Date().getFullYear()}-01-01`;
    return points.filter((p) => p.date >= yearStart);
  }
  if (tf === "1D") {
    return points.slice(-1);
  }
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - rule);
  const iso = cutoff.toISOString().slice(0, 10);
  return points.filter((p) => p.date >= iso);
}

// Fixed anchor range for the RTDB fetch — client-side filtering keeps
// tab switches instantaneous without refetching per timeframe.
export const FETCH_START = "2008-01-01";

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function cleanTicker(ticker: string): string {
  return ticker.replace(/\.(NR|KE)$/, "").replace(/_NR$/, "");
}
