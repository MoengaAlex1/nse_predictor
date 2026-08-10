import type { FC } from "react";

// Placeholder — a fuller valuation view lives on CompanyDeepDive
// (ValuationPanel). This card will surface the top-line P/S / P/B / EV
// figures once we settle on which subset to promote to the investor page.
export const FinancialsValuationCard: FC = () => (
  <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
    <div className="flex items-baseline justify-between">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Financials</p>
      <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-hint">
        Coming soon
      </span>
    </div>
    <div className="mt-2 flex flex-1 flex-col items-center justify-center">
      <p className="font-mono text-lg text-hint">—</p>
      <p className="text-[10px] text-hint">Valuation snapshot</p>
    </div>
  </div>
);
