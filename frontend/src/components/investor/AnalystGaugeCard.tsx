import type { FC } from "react";

// Placeholder — no analyst-consensus data source exists for NSE yet.
// Right-sized footprint so the Phase-E wiring drops in without relayout.
export const AnalystGaugeCard: FC = () => (
  <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
    <div className="flex items-baseline justify-between">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Analyst</p>
      <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-hint">
        Coming soon
      </span>
    </div>
    <div className="mt-2 flex flex-1 flex-col items-center justify-center gap-1">
      <div
        className="h-10 w-16 rounded-t-full border-2 border-dashed border-seam"
        aria-hidden="true"
      />
      <p className="text-[10px] text-hint">Consensus rating</p>
    </div>
  </div>
);
