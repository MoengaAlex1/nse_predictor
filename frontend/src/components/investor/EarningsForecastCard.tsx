import type { FC } from "react";

// Placeholder — fundamentals/{ticker}.estimates is schema-defined but not
// yet reliably populated across the ticker set. Wire in when the pipeline
// consistently emits EPS estimates.
export const EarningsForecastCard: FC = () => (
  <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
    <div className="flex items-baseline justify-between">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Earnings</p>
      <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-hint">
        Coming soon
      </span>
    </div>
    <div className="mt-2 flex flex-1 flex-col items-center justify-center">
      <p className="font-mono text-lg text-hint">—</p>
      <p className="text-[10px] text-hint">Next quarter forecast</p>
    </div>
  </div>
);
