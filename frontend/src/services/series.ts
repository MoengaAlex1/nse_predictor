/**
 * Derived series maths (phase 0 task 3).
 *
 * Everything here consumes the ADJUSTED bar series from getHistory +
 * adjustPrices — never companies.price_history, which carries decimal-scale
 * faults. EQTY's 52-week high read KES 7,625.00 on 2026-06-03 from that array;
 * the RTDB bar for the same session closes at 76.25, so the stored value is
 * exactly 100x out. See docs/data-audit.md.
 */
import type { Bar } from "./quotes";

export interface Range { high: number; low: number; from: string; to: string; observations: number }

/** Trailing-window high/low from adjusted closes. `today` is injectable. */
export function rangeOverDays(
  bars: Bar[],
  days: number,
  today: string = new Date().toISOString().slice(0, 10),
): Range | null {
  const cutoff = new Date(`${today}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - days);
  const cutIso = cutoff.toISOString().slice(0, 10);
  const window = bars.filter((b) => b.date >= cutIso && b.close != null);
  if (window.length === 0) return null;
  const closes = window.map((b) => b.close as number);
  return {
    high: Math.max(...closes),
    low: Math.min(...closes),
    from: window[0].date,
    to: window[window.length - 1].date,
    observations: window.length,
  };
}

export const fiftyTwoWeekRange = (bars: Bar[], today?: string) => rangeOverDays(bars, 365, today);

/** Where a price sits in a range, 0–100. Null when the range is degenerate. */
export function positionInRange(price: number | null, range: Range | null): number | null {
  if (price == null || range == null || range.high === range.low) return null;
  return Math.round(((price - range.low) / (range.high - range.low)) * 100);
}

/**
 * Simple return over a trailing window, as a percentage. Anchored on the last
 * close at or before the cutoff so a thin ticker is not measured from a gap.
 */
export function returnOverDays(
  bars: Bar[],
  days: number,
  today: string = new Date().toISOString().slice(0, 10),
): number | null {
  const withClose = bars.filter((b) => b.close != null);
  if (withClose.length < 2) return null;
  const cutoff = new Date(`${today}T00:00:00Z`);
  cutoff.setUTCDate(cutoff.getUTCDate() - days);
  const cutIso = cutoff.toISOString().slice(0, 10);
  const before = withClose.filter((b) => b.date <= cutIso);
  const anchor = before.length > 0 ? before[before.length - 1] : withClose[0];
  const last = withClose[withClose.length - 1];
  const a = anchor.close as number, b = last.close as number;
  if (a <= 0 || anchor.date === last.date) return null;
  return ((b - a) / a) * 100;
}
