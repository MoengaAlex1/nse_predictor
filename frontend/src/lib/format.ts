// Single source of truth for how prices, volumes, and deltas render across
// the investor shell. Every consumer should use these helpers so columns
// align (via tabular-nums), decimal counts match, and empty states share
// a consistent em-dash placeholder.

import type { CompanyDoc } from "../types";
import type { RtdbPricePoint } from "../hooks/useHistoricalPrices";

const emDash = "—";

const kesNf = new Intl.NumberFormat("en-KE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const compactNf = new Intl.NumberFormat("en-KE", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

// KES 4,201.75 — comma-thousands + 2 decimals + prefix.
export function fmtKes(v: number | null | undefined, opts: { prefix?: boolean } = {}): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  const s = kesNf.format(v);
  return opts.prefix === false ? s : `KES ${s}`;
}

// 4.74 — 2 decimals, no prefix, no thousands separator (chart axes).
export function fmtPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  return compactNf.format(v);
}

// +3.04% / −1.21% — always signed, always 2 decimals.
export function fmtPct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  const sign = v >= 0 ? "+" : "−"; // proper minus, not hyphen
  return `${sign}${Math.abs(v).toFixed(2)}%`;
}

// 23.44M / 5.13B / 998 — volume + shares outstanding + market cap.
export function fmtCompact(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  if (Math.abs(v) >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (Math.abs(v) >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toLocaleString("en-KE");
}

// KES 79.2B — compact currency with KES prefix (market cap card).
export function fmtCompactKes(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  return `KES ${fmtCompact(v)}`;
}

// Absolute price change with proper minus glyph and 2 decimals; unsigned.
// Direction is conveyed by an adjacent arrow/color in the layout, not here.
export function fmtChangeAbs(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  return kesNf.format(Math.abs(v));
}

// Signed price change (e.g. "+0.14" / "−0.32") used inline with the pct.
export function fmtChangeSigned(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return emDash;
  const sign = v >= 0 ? "+" : "−";
  return `${sign}${kesNf.format(Math.abs(v))}`;
}

export const arrow = (up: boolean): string => (up ? "▲" : "▼"); // ▲ / ▼
export const trendClass = (v: number | null | undefined, mutedWhenNull = "text-hint"): string => {
  if (v == null) return mutedWhenNull;
  return v >= 0 ? "text-emerald-500" : "text-red-500";
};

export const EM_DASH = emDash;

// ─────────────────────────────────────────────────────────────────────────────
// resolveDisplayPrice — single canonical resolver for "what price should I
// show for this ticker right now?" and its companion change fields. Every
// header, banner, sidebar tile, and OHLCV panel should call this so a
// single company never shows two different prices on the same page.
//
// Preference order (freshest source wins):
//   1. RTDB `latest.c`         — updated by scrape_nse_pdf + nse_price_cleaner
//   2. Firestore `current_price` — updated by push_intraday_prices + inference
//   3. Firestore `last_known_price` — seed_last_vwap Excel fallback
//
// changePct/changeAbs preference:
//   1. Compute from `(latest.c - latest.pc) / latest.pc` when both are present.
//   2. Fall back to `latest.pch`.
//   3. Fall back to Firestore `change_pct_today`.
//
// The resolver is a pure function — call it as many times as you like per
// render. It's placed here (not in a hook) so parent components can pass
// the resolved shape down to children without wrapping in another hook.
// ─────────────────────────────────────────────────────────────────────────────
export type DisplayPriceSource = "rtdb" | "firestore" | "last_known" | "none";

export interface DisplayPrice {
  price: number | null;
  previousClose: number | null;
  changePct: number | null;
  changeAbs: number | null;
  asOf: string | null;
  source: DisplayPriceSource;
  /** RTDB latest bar, if any — passthrough so downstream panels that need
   *  o/h/l/v alongside can read them without a second lookup. */
  latestBar: RtdbPricePoint | null;
}

export function resolveDisplayPrice(
  company: CompanyDoc | null | undefined,
  latest: RtdbPricePoint | null | undefined,
): DisplayPrice {
  const rtdbClose = latest?.c ?? null;
  const rtdbPrev = latest?.pc ?? null;

  let price: number | null = null;
  let source: DisplayPriceSource = "none";
  if (typeof rtdbClose === "number" && rtdbClose > 0) {
    price = rtdbClose;
    source = "rtdb";
  } else if (company?.current_price != null) {
    price = company.current_price;
    source = "firestore";
  } else if (company?.last_known_price != null) {
    price = company.last_known_price;
    source = "last_known";
  }

  let changeAbs: number | null = null;
  let changePct: number | null = null;
  if (price != null && typeof rtdbPrev === "number" && rtdbPrev > 0) {
    changeAbs = price - rtdbPrev;
    changePct = (changeAbs / rtdbPrev) * 100;
  } else if (latest?.pch != null) {
    changePct = latest.pch;
    changeAbs = latest.ch ?? null;
  } else if (company?.change_pct_today != null) {
    changePct = company.change_pct_today;
  }

  const asOf = latest?.date ?? company?.price_date ?? null;

  return {
    price,
    previousClose: rtdbPrev,
    changePct,
    changeAbs,
    asOf,
    source,
    latestBar: latest ?? null,
  };
}
