/**
 * The ONLY price accessor in the app.
 *
 * Source of truth is RTDB `prices/{ticker}/{YYYY-MM-DD}`, not Firestore.
 * See docs/data-audit.md: all 61 `companies/*` docs carry `current_price = null`
 * because the daily pipeline swallows per-ticker exceptions and still exits 0,
 * so anything reading `companies.current_price` gets null and anything falling
 * back to `companies.last_known_price` gets a VWAP dated 2023-09-30. That
 * fallback is the KES 37.60 that /screener showed for EQTY against a real close
 * of 106.00. It is deliberately NOT a tier in this module.
 *
 * No component may compute a price, market cap or ratio from its own query.
 */
import { ref, query, orderByKey, startAt, endAt, limitToLast, get } from "firebase/database";
import { rtdb } from "../lib/rtdb";
import { shortFromDisplayTicker, isShort } from "../lib/identity";

/** How a close was arrived at. Never silently substituted — always tagged. */
export type QuoteSource = "trade" | "vwap" | "carry-forward";

export interface Quote {
  ticker: string;
  /** Date of the bar the price came from, not "today". */
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  prevClose: number | null;
  change: number | null;
  changePct: number | null;
  volume: number | null;
  vwap: number | null;
  /** True when the newest usable bar is more than STALE_AFTER_DAYS trading days old. */
  isStale: boolean;
  /** Trading days (weekdays) between the bar date and today. 0 = today. */
  staleDays: number;
  source: QuoteSource;
}

export interface Bar {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  prevClose: number | null;
  change: number | null;
  changePct: number | null;
  volume: number | null;
  vwap: number | null;
}

/** Raw RTDB bar shape. `vv` is the traded-value/VWAP slot; frequently null. */
interface RawBar {
  o: number | null; h: number | null; l: number | null; c: number | null;
  v: number | null; pc: number | null; ch: number | null; pch: number | null;
  vv?: number | null;
}

export const STALE_AFTER_DAYS = 3;

/**
 * A single-session move beyond this is treated as a data fault unless a
 * corporate action explains it. EQTY's 7,625 print is exactly this case.
 */
export const MAX_SESSION_MOVE = 0.35;

/** How many trailing bars getQuote pulls to find the newest usable one. */
const LOOKBACK_BARS = 15;

export interface RejectedBar {
  ticker: string;
  date: string;
  close: number;
  prevClose: number;
  movePct: number;
  reason: "move-exceeds-threshold";
}

/** Corporate-action dates per ticker; Phase 0 task 3 supplies the real source. */
export type CorporateActionIndex = ReadonlySet<string>;
const NO_ACTIONS: CorporateActionIndex = new Set<string>();

function canonical(ticker: string): string {
  return isShort(ticker) ? ticker : shortFromDisplayTicker(ticker);
}

function toBar(date: string, r: RawBar): Bar {
  return {
    date,
    open: r.o ?? null,
    high: r.h ?? null,
    low: r.l ?? null,
    close: r.c ?? null,
    prevClose: r.pc ?? null,
    change: r.ch ?? null,
    changePct: r.pch ?? null,
    volume: r.v ?? null,
    vwap: r.vv ?? null,
  };
}

/**
 * A bar is rejected when it moves more than MAX_SESSION_MOVE against its own
 * prevClose and no corporate action is recorded for that date. Rejected bars
 * are dropped from the series and logged rather than repaired, so a bad tick
 * can never reach an indicator or a 52-week range.
 */
export function isFaultyBar(bar: Bar, actions: CorporateActionIndex = NO_ACTIONS): boolean {
  if (bar.close == null || bar.prevClose == null || bar.prevClose <= 0) return false;
  if (actions.has(bar.date)) return false;
  // Compared as |close - prevClose| > threshold * prevClose rather than
  // |close / prevClose - 1| > threshold: the ratio form loses precision in the
  // subtraction (1.35 - 1 is 0.35000000000000009), so a move of exactly the
  // threshold would be rejected by a rule that says "beyond" it.
  return Math.abs(bar.close - bar.prevClose) > MAX_SESSION_MOVE * bar.prevClose;
}

function partitionFaulty(
  ticker: string,
  bars: Bar[],
  actions: CorporateActionIndex,
): { clean: Bar[]; rejected: RejectedBar[] } {
  const clean: Bar[] = [];
  const rejected: RejectedBar[] = [];
  for (const b of bars) {
    if (isFaultyBar(b, actions)) {
      rejected.push({
        ticker,
        date: b.date,
        close: b.close as number,
        prevClose: b.prevClose as number,
        movePct: ((b.close as number) / (b.prevClose as number) - 1) * 100,
        reason: "move-exceeds-threshold",
      });
    } else {
      clean.push(b);
    }
  }
  if (rejected.length > 0) {
    // Loud on purpose: a silent drop is how bad data becomes a silent wrong answer.
    console.warn(
      `[quotes] ${ticker}: rejected ${rejected.length} bar(s) exceeding ` +
        `${(MAX_SESSION_MOVE * 100).toFixed(0)}% with no corporate action`,
      rejected,
    );
  }
  return { clean, rejected };
}

/** Weekday count between two ISO dates. Holidays are not modelled. */
export function tradingDaysBetween(fromIso: string, toIso: string): number {
  const from = new Date(`${fromIso}T00:00:00Z`);
  const to = new Date(`${toIso}T00:00:00Z`);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to <= from) return 0;
  let days = 0;
  const cur = new Date(from);
  cur.setUTCDate(cur.getUTCDate() + 1);
  while (cur <= to) {
    const dow = cur.getUTCDay();
    if (dow !== 0 && dow !== 6) days++;
    cur.setUTCDate(cur.getUTCDate() + 1);
  }
  return days;
}

/**
 * Classify how the close was obtained:
 *  - trade         : the security actually traded (volume > 0 and a close)
 *  - vwap          : no close, but a VWAP/traded-value figure exists
 *  - carry-forward : a close with no volume — the exchange rolled the price
 */
function classify(bar: Bar): QuoteSource | null {
  if (bar.close != null && bar.volume != null && bar.volume > 0) return "trade";
  if (bar.close == null && bar.vwap != null) return "vwap";
  if (bar.close != null) return "carry-forward";
  return null;
}

async function fetchRecentBars(ticker: string, count: number): Promise<Bar[]> {
  const snap = await get(query(ref(rtdb, `prices/${ticker}`), orderByKey(), limitToLast(count)));
  if (!snap.exists()) return [];
  const val = snap.val() as Record<string, RawBar>;
  return Object.entries(val)
    .map(([date, raw]) => toBar(date, raw))
    .sort((a, b) => a.date.localeCompare(b.date));
}

/**
 * Latest quote for one ticker. Returns null when the ticker has no usable bar
 * at all — callers render an em dash, never a zero.
 */
export async function getQuote(
  rawTicker: string,
  opts: { today?: string; actions?: CorporateActionIndex } = {},
): Promise<Quote | null> {
  const ticker = canonical(rawTicker);
  if (!ticker) return null;
  const actions = opts.actions ?? NO_ACTIONS;
  const today = opts.today ?? new Date().toISOString().slice(0, 10);

  const { clean } = partitionFaulty(ticker, await fetchRecentBars(ticker, LOOKBACK_BARS), actions);
  if (clean.length === 0) return null;

  // Newest bar that yields a usable price, walking backwards.
  for (let i = clean.length - 1; i >= 0; i--) {
    const bar = clean[i];
    const source = classify(bar);
    if (!source) continue;

    const close = bar.close ?? bar.vwap;
    const prevClose = bar.prevClose ?? clean[i - 1]?.close ?? null;
    const change =
      bar.change ?? (close != null && prevClose != null ? close - prevClose : null);
    const changePct =
      bar.changePct ??
      (close != null && prevClose != null && prevClose > 0
        ? ((close - prevClose) / prevClose) * 100
        : null);
    const staleDays = tradingDaysBetween(bar.date, today);

    return {
      ticker,
      date: bar.date,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close,
      prevClose,
      change,
      changePct,
      volume: bar.volume,
      vwap: bar.vwap,
      isStale: staleDays > STALE_AFTER_DAYS,
      staleDays,
      source,
    };
  }
  return null;
}

/**
 * Batched latest quotes.
 *
 * The plan specified "one Firestore read", but the source moved to RTDB, where
 * only `prices/*` is world-readable (database.rules.json) and there is no
 * multi-path query. So this fans out one small limitToLast read per ticker in
 * parallel — 61 bounded reads, not a whole-collection scan.
 */
export async function getQuotes(
  tickers: string[],
  opts: { today?: string; actions?: CorporateActionIndex } = {},
): Promise<Map<string, Quote>> {
  const unique = Array.from(new Set(tickers.map(canonical).filter(Boolean)));
  const settled = await Promise.all(
    unique.map(async (t) => {
      try {
        return await getQuote(t, opts);
      } catch (err) {
        console.warn(`[quotes] ${t}: quote fetch failed`, err);
        return null;
      }
    }),
  );
  const out = new Map<string, Quote>();
  settled.forEach((q) => { if (q) out.set(q.ticker, q); });
  return out;
}

export interface HistoryRange { from: string; to: string }

/**
 * OHLCV series with faulty bars removed. Corporate-action back-adjustment is
 * applied by the caller in phase 0 task 3 via `adjustPrices`; this returns the
 * cleaned raw series so the unadjusted OHLC quote block can still use it.
 */
export async function getHistory(
  rawTicker: string,
  range: HistoryRange,
  opts: { actions?: CorporateActionIndex } = {},
): Promise<Bar[]> {
  const ticker = canonical(rawTicker);
  if (!ticker || !range.from || !range.to) return [];
  const snap = await get(
    query(ref(rtdb, `prices/${ticker}`), orderByKey(), startAt(range.from), endAt(range.to)),
  );
  if (!snap.exists()) return [];
  const val = snap.val() as Record<string, RawBar>;
  const bars = Object.entries(val)
    .map(([date, raw]) => toBar(date, raw))
    .sort((a, b) => a.date.localeCompare(b.date));
  return partitionFaulty(ticker, bars, opts.actions ?? NO_ACTIONS).clean;
}
