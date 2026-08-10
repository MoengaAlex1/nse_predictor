import type { FC } from "react";

// Placeholder — ensemble prediction is available via useLatestSnapshot but
// the user asked to defer wiring "as we progress working on it". When wiring
// in, this becomes signal.predicted_price_KES + predicted_change_pct with an
// explicit "Model Target" label (never "Analyst Target").
export const ModelTargetCard: FC = () => (
  <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
    <div className="flex items-baseline justify-between">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Model Target</p>
      <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-hint">
        Coming soon
      </span>
    </div>
    <div className="mt-2 flex flex-1 flex-col items-center justify-center">
      <p className="font-mono text-lg text-hint">—</p>
      <p className="text-[10px] text-hint">Ensemble prediction</p>
    </div>
  </div>
);
