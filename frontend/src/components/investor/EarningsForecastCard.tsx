import type { FC } from "react";
import type { FundamentalsDoc } from "../../types";

interface Props {
  /**
   * FundamentalsDoc from Firestore. Its `estimates` array carries the
   * next-period EPS / revenue projections tagged with a `consensus` or
   * `management` source; that source becomes the chip on this tile so users
   * see at a glance whether the number came from sell-side aggregation or
   * from the company's own guidance.
   */
  fundamentals?: FundamentalsDoc | null;
}

/**
 * Earnings forecast tile — displays the next-period EPS estimate (or revenue
 * when EPS is missing), pulled from fundamentals.estimates. Kenyan-listed
 * companies rarely publish full sell-side EPS forecasts, so most tickers
 * will land in the "No estimate" state until the pipeline consistently
 * emits data for them — which is exactly what the original placeholder
 * comment on this file warned about.
 *
 * The source chip matters: `management` guidance is far more common than
 * analyst `consensus` on NSE, and the label makes that provenance explicit
 * rather than conflating the two.
 */
export const EarningsForecastCard: FC<Props> = ({ fundamentals }) => {
  // Sort estimates by period ascending so the nearest unreported period is
  // first. Period strings on this doc are ISO-ish ("FY2025", "H1 2026") but
  // localeCompare is stable enough for the ordering we care about.
  const estimates = fundamentals?.estimates?.slice().sort((a, b) =>
    a.period.localeCompare(b.period)
  ) ?? [];
  const next = estimates[0];

  const hasNumber = next && (next.eps_kes != null || next.revenue_kes_mn != null);
  if (!hasNumber) {
    return (
      <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
        <div className="flex items-baseline justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Earnings</p>
          <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-hint">
            No estimate
          </span>
        </div>
        <div className="mt-2 flex flex-1 flex-col items-center justify-center">
          <p className="font-mono text-lg text-hint">—</p>
          <p className="text-[10px] text-hint">Next-period EPS</p>
        </div>
      </div>
    );
  }

  // Prefer EPS when available — that's what MSN's Earnings tile displays and
  // it's what most Kenyan retail readers track. Revenue is the fallback so
  // the tile has SOMETHING when the estimate covers only top-line guidance.
  const showEps = next.eps_kes != null;
  const value   = showEps
    ? `KES ${next.eps_kes!.toFixed(2)}`
    : `KES ${(next.revenue_kes_mn! / 1000).toFixed(2)}B`;
  const label   = showEps ? "EPS" : "Revenue";

  return (
    <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Earnings</p>
        <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-muted">
          {next.source}
        </span>
      </div>
      <div className="mt-2 flex flex-1 flex-col items-center justify-center gap-0.5">
        <p className="font-mono text-lg font-bold text-ink">{value}</p>
        <p className="text-[10px] text-hint">{label} · {next.period}</p>
        {next.pe_forward != null && (
          <p className="text-[10px] text-hint">Fwd P/E {next.pe_forward.toFixed(1)}x</p>
        )}
      </div>
    </div>
  );
};
