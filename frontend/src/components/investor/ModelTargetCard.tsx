import type { FC } from "react";
import type { SnapshotDoc } from "../../types";

interface Props {
  /**
   * Latest ensemble prediction from Firestore (SnapshotDoc). When absent, the
   * card falls back to a labelled "no data" state — never a fabricated target.
   */
  snapshot?: SnapshotDoc | null;
  currentPrice?: number | null;
}

const signalStyle = (signal: SnapshotDoc["risk_adjusted_signal"]): string => {
  switch (signal) {
    case "BUY":  return "border-emerald-500/40 bg-emerald-500/10 text-emerald-500";
    case "SELL": return "border-red-500/40 bg-red-500/10 text-red-500";
    default:     return "border-seam bg-raised text-muted";
  }
};

/**
 * Ensemble price prediction tile.
 *
 * The card is deliberately labelled "Model Target" (never "Analyst Target") —
 * these are model outputs from the ARIMA + LSTM + XGBoost ensemble persisted
 * on the SnapshotDoc, not analyst-consensus estimates. Wired to snapshot
 * fields per the note in the previous placeholder version of this file:
 *
 *   predicted_price_KES   — model's next-close estimate in KES
 *   predicted_change_pct  — implied delta vs the current close, signed
 *   risk_adjusted_signal  — BUY / HOLD / SELL bucket that risk-adjusts the raw
 *                           forecast (fed into the top-right chip)
 *
 * currentPrice is accepted for future compare-vs-live but not yet used
 * visually — the ensemble already publishes predicted_change_pct so we render
 * the sign directly rather than recomputing it and risking a mismatch with
 * whichever price feed the header is currently showing.
 */
export const ModelTargetCard: FC<Props> = ({ snapshot }) => {
  const target    = snapshot?.predicted_price_KES ?? null;
  const changePct = snapshot?.predicted_change_pct ?? null;
  const signal    = snapshot?.risk_adjusted_signal;

  if (target == null) {
    return (
      <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
        <div className="flex items-baseline justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Model Target</p>
          <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-hint">
            No data
          </span>
        </div>
        <div className="mt-2 flex flex-1 flex-col items-center justify-center">
          <p className="font-mono text-lg text-hint">—</p>
          <p className="text-[10px] text-hint">Ensemble prediction</p>
        </div>
      </div>
    );
  }

  const isUp = (changePct ?? 0) >= 0;
  const changeColor = isUp ? "text-emerald-500" : "text-red-500";

  return (
    <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Model Target</p>
        {signal && (
          <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${signalStyle(signal)}`}>
            {signal}
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-1 flex-col items-center justify-center gap-0.5">
        <p className="font-mono text-lg font-bold text-ink">
          KES {target.toFixed(2)}
        </p>
        {changePct != null && (
          <p className={`font-mono text-xs font-semibold ${changeColor}`}>
            {isUp ? "▲" : "▼"} {isUp ? "+" : ""}{changePct.toFixed(2)}%
          </p>
        )}
        <p className="text-[10px] text-hint">Ensemble prediction</p>
      </div>
    </div>
  );
};
