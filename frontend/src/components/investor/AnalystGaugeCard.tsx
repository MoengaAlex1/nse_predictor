import type { FC } from "react";
import type { SnapshotDoc } from "../../types";

interface Props {
  /**
   * Latest SnapshotDoc from Firestore. When absent, the card renders a
   * labelled "no data" state instead of a fabricated rating.
   */
  snapshot?: SnapshotDoc | null;
}

const signalStyle = (signal: SnapshotDoc["risk_adjusted_signal"]): string => {
  switch (signal) {
    case "BUY":  return "border-emerald-500/40 bg-emerald-500/10 text-emerald-500";
    case "SELL": return "border-red-500/40 bg-red-500/10 text-red-500";
    default:     return "border-seam bg-raised text-muted";
  }
};

const barTint = (signal: SnapshotDoc["risk_adjusted_signal"]): string => {
  switch (signal) {
    case "BUY":  return "bg-emerald-500";
    case "SELL": return "bg-red-500";
    default:     return "bg-muted";
  }
};

/**
 * Model-signal tile — the ensemble's BUY/HOLD/SELL vote plus a bar showing
 * how much the three constituent models (LSTM, XGBoost, ARIMA) agree.
 *
 * The card is deliberately labelled "Model Signal" in the heading, not
 * "Analyst." NSE-listed tickers do not have professional sell-side analyst
 * coverage of the kind MSN Money's US pages show ("Hold — 48 analysts"), so
 * using that language would fabricate coverage that doesn't exist. The
 * ensemble's own vote is the closest honest analogue and is what we display.
 *
 * ModelTargetCard shows the same snapshot from the PRICE side (predicted
 * KES + change %); this tile is the SIGNAL side (BUY/HOLD/SELL + agreement).
 */
/**
 * Return a 0..100 integer percentage for a value that may be stored either as
 * a 0..1 fraction (older Snapshot writers) or already as a 0..100 percentage
 * (recent pipeline versions). Anything above 1 is treated as already-scaled;
 * that heuristic is safe here because a real agreement / confidence fraction
 * can never itself exceed 1.
 */
const asPct = (v: number | null | undefined): number | null =>
  v == null ? null : Math.round(v > 1 ? v : v * 100);

export const AnalystGaugeCard: FC<Props> = ({ snapshot }) => {
  const signal     = snapshot?.risk_adjusted_signal;
  const agreement  = snapshot?.model_agreement;
  const confidence = snapshot?.confidence_score;

  if (!signal) {
    return (
      <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
        <div className="flex items-baseline justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Model Signal</p>
          <span className="rounded-full border border-seam bg-raised px-1.5 py-0.5 text-[9px] font-semibold text-hint">
            No data
          </span>
        </div>
        <div className="mt-2 flex flex-1 flex-col items-center justify-center gap-1">
          <div className="h-10 w-16 rounded-t-full border-2 border-dashed border-seam" aria-hidden="true" />
          <p className="text-[10px] text-hint">Ensemble vote</p>
        </div>
      </div>
    );
  }

  const agreementPct  = asPct(agreement);
  const confidencePct = asPct(confidence);
  // Guard against oversized bars if the source data is already >100 for some
  // legacy row — the visual max is 100.
  const barPct = agreementPct != null ? Math.min(100, agreementPct) : 0;

  return (
    <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-3">
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Model Signal</p>
        <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${signalStyle(signal)}`}>
          {signal}
        </span>
      </div>
      <div className="mt-2 flex flex-1 flex-col items-center justify-center gap-1">
        <p className="font-mono text-lg font-bold text-ink">
          {agreementPct != null ? `${agreementPct}%` : "—"}
        </p>
        <p className="text-[10px] text-hint">Model agreement</p>
        {agreementPct != null && (
          <div className="mt-1 h-1.5 w-full max-w-[110px] overflow-hidden rounded-full bg-raised">
            <div
              className={`h-full ${barTint(signal)} transition-all`}
              style={{ width: `${barPct}%` }}
              aria-hidden="true"
            />
          </div>
        )}
        {confidencePct != null && (
          <p className="text-[10px] text-hint">Confidence {confidencePct}%</p>
        )}
      </div>
    </div>
  );
};
