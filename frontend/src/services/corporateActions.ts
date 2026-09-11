/**
 * Corporate actions and price back-adjustment (phase 0 task 3).
 *
 * The plan called for a new `corporateActions` collection, but the data is
 * already stored per ticker at `financials/{id}.corporate_actions`, written by
 * pipeline/scripts/scrape_nse_daily_bulletins.py with typed ratio fields. A
 * second collection would be a second truth, so this reads the existing one.
 *
 * Every indicator, return and 52-week range must consume the ADJUSTED series.
 * The unadjusted series is only for the raw OHLC quote block.
 */
import type { CorporateAction } from "../types";
import type { Bar, CorporateActionIndex } from "./quotes";

/** Action types that change the price basis and so require back-adjustment. */
const ADJUSTING_TYPES = new Set(["split", "bonus"]);

function normType(a: CorporateAction): string {
  return (a.type ?? "").toLowerCase().trim();
}

/** The date an action takes effect. Books-closure/ex date wins over announcement. */
export function effectiveDate(a: CorporateAction): string | null {
  return a.ex_date ?? a.date ?? null;
}

/**
 * Price multiplier applied to every bar BEFORE the ex-date.
 *
 *  - split  "N new for M old"  -> holders end with N per M, price basis M/N
 *  - bonus  "N for M held"     -> holders end with M+N per M, basis M/(M+N)
 *
 * Returns null when the action does not move the price basis or the ratio is
 * unusable — callers then leave the series alone rather than guessing.
 */
export function adjustmentFactor(a: CorporateAction): number | null {
  const type = normType(a);
  if (!ADJUSTING_TYPES.has(type)) return null;
  const nw = a.ratio_new;
  const old = a.ratio_old;
  if (nw == null || old == null || nw <= 0 || old <= 0) return null;
  if (type === "split") return old / nw;
  return old / (old + nw); // bonus
}

/** Dates that legitimately explain a large single-session move. */
export function actionDateIndex(actions: CorporateAction[] | undefined): CorporateActionIndex {
  const out = new Set<string>();
  (actions ?? []).forEach((a) => {
    const d = effectiveDate(a);
    if (d) out.add(d);
  });
  return out;
}

/**
 * Back-adjust an ascending OHLCV series for splits and bonuses.
 *
 * Each qualifying action scales every bar strictly before its ex-date. Applied
 * newest-first so multiple actions compound correctly. Volume is scaled by the
 * inverse so traded value is preserved.
 */
export function adjustPrices(bars: Bar[], actions: CorporateAction[] | undefined): Bar[] {
  if (bars.length === 0) return bars;
  const applicable = (actions ?? [])
    .map((a) => ({ date: effectiveDate(a), factor: adjustmentFactor(a) }))
    .filter((a): a is { date: string; factor: number } => a.date != null && a.factor != null)
    .sort((a, b) => b.date.localeCompare(a.date));
  if (applicable.length === 0) return bars;

  let out = bars;
  for (const { date, factor } of applicable) {
    out = out.map((b) => {
      if (b.date >= date) return b;
      const px = (v: number | null) => (v == null ? null : v * factor);
      return {
        ...b,
        open: px(b.open),
        high: px(b.high),
        low: px(b.low),
        close: px(b.close),
        prevClose: px(b.prevClose),
        vwap: px(b.vwap),
        change: px(b.change),
        // changePct is scale-invariant; volume scales inversely.
        volume: b.volume == null ? null : b.volume / factor,
      };
    });
  }
  return out;
}
