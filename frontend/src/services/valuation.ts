/**
 * The single place market cap and every valuation ratio is computed
 * (phase 0 tasks 4 and 5).
 *
 * Before this, market cap existed twice — Screener.tsx:49 and
 * RightStatsRail.tsx:78 — with the same multiplier but different price tiers,
 * which is why one route showed KES 141.98B and the other an em dash.
 *
 * Rule for every export here: return null when any input is missing or the
 * denominator is <= 0. Never 0.0x, never 0.00%, never KES 0.00. The UI renders
 * null as an em dash. `ValuationPanel.tsx:49` previously did
 * `current_price ?? 0`, which turned a null price into a real-looking 0.0x P/E.
 */
import type { FinancialResult, FinancialsDoc, FundamentalsDoc } from "../types";

/** A figure plus the period it came from, so the UI can always label it. */
export interface Dated<T> {
  value: T;
  asOf: string | null;
  fiscalPeriod: string | null;
}

function dated<T>(value: T, asOf: string | null, fiscalPeriod: string | null): Dated<T> {
  return { value, asOf, fiscalPeriod };
}

/** Market cap in KES. The ONLY market-cap computation in the app. */
export function marketCap(
  close: number | null | undefined,
  sharesOutstandingMn: number | null | undefined,
): number | null {
  if (close == null || sharesOutstandingMn == null) return null;
  if (close <= 0 || sharesOutstandingMn <= 0) return null;
  return close * sharesOutstandingMn * 1_000_000;
}

/** Shares outstanding as an absolute count, from the millions-denominated field. */
export function sharesOutstanding(sharesOutstandingMn: number | null | undefined): number | null {
  if (sharesOutstandingMn == null || sharesOutstandingMn <= 0) return null;
  return sharesOutstandingMn * 1_000_000;
}

/** Where a figure came from, so the UI can always attribute it. */
export interface Sourced<T> extends Dated<T> {
  source: string;
}

/**
 * Share count with its as-of date and source (phase 0 task 4). One field per
 * ticker, one place it is read. Returns null rather than a zero so a missing
 * count renders as an em dash and market cap stays null with it.
 */
export function sharesOutstandingDated(
  fundamentals: Pick<FundamentalsDoc, "shares_outstanding_mn" | "updated_at"> | null | undefined,
  ticker?: string,
): Sourced<number> | null {
  const n = sharesOutstanding(fundamentals?.shares_outstanding_mn);
  if (n == null) return null;
  return {
    value: n,
    asOf: fundamentals?.updated_at ?? null,
    fiscalPeriod: null,
    source: ticker ? `fundamentals/${ticker}` : "fundamentals",
  };
}

/** Why a figure is missing, for the em-dash tooltip (phase 0 task 5). */
export function missingReason(
  price: number | null | undefined,
  input: number | null | undefined,
  inputLabel: string,
): string {
  if (price == null) return "No price available for this security";
  if (price <= 0) return "Price is not positive";
  if (input == null) return `No ${inputLabel} reported`;
  if (input <= 0) return `${inputLabel} is not positive, so the ratio is not meaningful`;
  return "Not available";
}

/** Most recent annual result carrying a usable EPS. */
export function latestAnnualEps(fin: FinancialsDoc | undefined): Dated<number> | null {
  const annuals = [...(fin?.annual ?? [])].sort((a, b) =>
    (b.period_end ?? "").localeCompare(a.period_end ?? ""),
  );
  const row: FinancialResult | undefined = annuals.find((r) => r.eps != null && r.eps > 0);
  if (!row || row.eps == null) return null;
  return dated(row.eps, row.period_end ?? null, row.period ?? null);
}

/** Most recent annual book value per share. */
export function latestAnnualBvps(fin: FinancialsDoc | undefined): Dated<number> | null {
  const annuals = [...(fin?.annual ?? [])].sort((a, b) =>
    (b.period_end ?? "").localeCompare(a.period_end ?? ""),
  );
  const row = annuals.find((r) => r.bvps != null && r.bvps > 0);
  if (!row || row.bvps == null) return null;
  return dated(row.bvps, row.period_end ?? null, row.period ?? null);
}

export function priceEarnings(
  close: number | null | undefined,
  eps: number | null | undefined,
): number | null {
  if (close == null || eps == null || close <= 0 || eps <= 0) return null;
  return close / eps;
}

export function priceToBook(
  close: number | null | undefined,
  bvps: number | null | undefined,
): number | null {
  if (close == null || bvps == null || close <= 0 || bvps <= 0) return null;
  return close / bvps;
}

/**
 * Trailing-twelve-month dividend yield as a percentage.
 * `now` is injectable so the window is testable.
 */
export function dividendYieldTtm(
  fin: FinancialsDoc | undefined,
  close: number | null | undefined,
  now: Date = new Date(),
): number | null {
  if (close == null || close <= 0) return null;
  const dividends = fin?.dividends ?? [];
  if (dividends.length === 0) return null;
  const cutoff = new Date(now);
  cutoff.setFullYear(cutoff.getFullYear() - 1);
  const cutIso = cutoff.toISOString().slice(0, 10);
  const nowIso = now.toISOString().slice(0, 10);
  let total = 0;
  dividends.forEach((d) => {
    // Window is bounded at BOTH ends. The original screener logic only had a
    // lower bound, so a dividend announced after `now` counted toward a
    // "trailing" twelve months.
    if (
      d.type !== "none" &&
      d.amount_kes != null &&
      d.announcement_date >= cutIso &&
      d.announcement_date <= nowIso
    ) {
      total += d.amount_kes;
    }
  });
  if (total <= 0) return null;
  return (total / close) * 100;
}
