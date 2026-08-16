import type { FC } from "react";
import type { FinancialsDoc } from "../../types";

interface Props {
  /**
   * FinancialsDoc from Firestore. The `annual` array carries EPS and BVPS
   * per reported fiscal year; the tile displays the most recent one and
   * combines it with the live price to derive a trailing P/E ratio.
   */
  financials?: FinancialsDoc | null;
  /** Current market price in KES — used to compute trailing P/E. */
  currentPrice?: number | null;
}

/**
 * Latest-annual valuation snapshot — displays trailing P/E when both a
 * current price and a positive latest EPS are available, otherwise EPS
 * alone. The tile is deliberately labelled "Trailing P/E" (not just "P/E")
 * because forward P/E lives on the Earnings tile — showing both means the
 * user can tell at a glance whether the market is priced ahead of or behind
 * the ensemble's next-period forecast.
 */
export const FinancialsValuationCard: FC<Props> = ({ financials, currentPrice }) => {
  // Sort annual results by period_end descending so the most recent one is
  // first. period_end is an ISO date string, so localeCompare is stable.
  const annual = financials?.annual?.slice().sort((a, b) =>
    b.period_end.localeCompare(a.period_end)
  ) ?? [];
  const latest = annual[0];
  const eps    = latest?.eps ?? null;
  // Guard against divide-by-zero and negative-EPS P/E — a negative trailing
  // P/E isn't meaningful to display as a valuation multiple.
  const pe = currentPrice != null && eps != null && eps > 0
    ? currentPrice / eps
    : null;

  if (eps == null) {
    return (
      <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
        <div className="flex items-baseline justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Financials</p>
          <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-hint">
            No data
          </span>
        </div>
        <div className="mt-2 flex flex-1 flex-col items-center justify-center">
          <p className="font-mono text-lg text-hint">—</p>
          <p className="text-[10px] text-hint">Valuation snapshot</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Financials</p>
        <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-muted">
          {latest.period}
        </span>
      </div>
      <div className="mt-2 flex flex-1 flex-col items-center justify-center gap-0.5">
        {pe != null ? (
          <>
            <p className="font-mono text-lg font-bold text-ink">{pe.toFixed(1)}x</p>
            <p className="text-[10px] text-hint">Trailing P/E</p>
            <p className="text-[10px] text-hint">EPS KES {eps.toFixed(2)}</p>
          </>
        ) : (
          <>
            <p className="font-mono text-lg font-bold text-ink">KES {eps.toFixed(2)}</p>
            <p className="text-[10px] text-hint">EPS · {latest.period}</p>
          </>
        )}
      </div>
    </div>
  );
};
