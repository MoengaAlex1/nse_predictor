/**
 * Model-output guardrails (phase 3 task 2).
 *
 * The shipped panel reported, for EQTY: ensemble SELL, target KES 60.42
 * labelled -9.90%, from components LSTM 42.33, ARIMA 106.00, XGBoost 56.56,
 * with RMSE 486 and MAPE 20.1% against a KES 106 price.
 *
 * Three separate defects:
 *   1. 106.00 -> 60.42 is -43%, not -9.90%. The headline did not reconcile
 *      with its own target.
 *   2. -9.90% did not reconcile with any combination of the components either.
 *   3. An RMSE of 486 on a 106-shilling stock means the outputs were not on
 *      the price scale at all.
 *
 * Nothing here retrains anything. It decides what may be displayed, and states
 * plainly what was excluded and why.
 */

/** A model target outside this band of last close is not a forecast. */
export const MIN_TARGET_RATIO = 0.4;
export const MAX_TARGET_RATIO = 2.5;
/** Above this MAPE a model may not drive the headline signal. */
export const MAX_RELIABLE_MAPE = 10;

export type ModelStatus = "ok" | "errored" | "low-reliability";

export interface ModelOutput {
  name: string;
  target: number | null;
  /** Mean absolute percentage error from backtesting, in percent. */
  mape?: number | null;
  /** Root mean squared error in KES. */
  rmse?: number | null;
}

export interface CheckedModel extends ModelOutput {
  status: ModelStatus;
  /** Why it was excluded, for display. Null when status is "ok". */
  reason: string | null;
  /** Implied move from last close, in percent. Null when unusable. */
  impliedPct: number | null;
  /** RMSE as a percentage of last close — the scale-sanity figure. */
  rmsePctOfPrice: number | null;
}

export interface Ensemble {
  models: CheckedModel[];
  surviving: CheckedModel[];
  /** Median of surviving targets. Null when none survive. */
  target: number | null;
  impliedPct: number | null;
  /** The rule, stated for display rather than implied. */
  rule: string;
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

/**
 * Classify one model against the last close. A target outside the sanity band
 * is ERRORED and excluded — never rendered as if it were a forecast.
 */
export function checkModel(model: ModelOutput, lastClose: number | null): CheckedModel {
  const base: CheckedModel = {
    ...model, status: "ok", reason: null, impliedPct: null, rmsePctOfPrice: null,
  };
  if (lastClose == null || lastClose <= 0) {
    return { ...base, status: "errored", reason: "No price to compare the target against" };
  }
  if (model.target == null || !Number.isFinite(model.target) || model.target <= 0) {
    return { ...base, status: "errored", reason: "Model produced no usable target" };
  }

  const ratio = model.target / lastClose;
  const impliedPct = (ratio - 1) * 100;
  const rmsePctOfPrice = model.rmse != null ? (model.rmse / lastClose) * 100 : null;
  const withNumbers = { ...base, impliedPct, rmsePctOfPrice };

  if (ratio < MIN_TARGET_RATIO || ratio > MAX_TARGET_RATIO) {
    return {
      ...withNumbers,
      status: "errored",
      reason:
        `Target is ${ratio.toFixed(2)}x the last close, outside the ` +
        `${MIN_TARGET_RATIO}x–${MAX_TARGET_RATIO}x sanity band — treated as a scale fault`,
    };
  }
  if (model.mape != null && model.mape > MAX_RELIABLE_MAPE) {
    return {
      ...withNumbers,
      status: "low-reliability",
      reason: `Backtest MAPE of ${model.mape.toFixed(1)}% exceeds ${MAX_RELIABLE_MAPE}%`,
    };
  }
  return withNumbers;
}

/**
 * Build the ensemble from the surviving models only. The headline target is
 * the median of those, and the rule is returned as text so the UI can state it
 * rather than leave the user to infer it.
 */
export function buildEnsemble(models: ModelOutput[], lastClose: number | null): Ensemble {
  const checked = models.map((m) => checkModel(m, lastClose));
  const surviving = checked.filter((m) => m.status === "ok");
  const target = median(surviving.map((m) => m.target as number));
  const impliedPct =
    target != null && lastClose != null && lastClose > 0
      ? ((target - lastClose) / lastClose) * 100
      : null;
  const rule =
    surviving.length === 0
      ? "No model passed the sanity checks — no ensemble target"
      : `Median of ${surviving.length} surviving model${surviving.length === 1 ? "" : "s"}` +
        ` (${surviving.map((m) => m.name).join(", ")})`;
  return { models: checked, surviving, target, impliedPct, rule };
}

/**
 * Confidence from realised out-of-sample hit rate, not model agreement.
 * Agreement between three models that are all wrong is not confidence.
 */
export function confidenceFromHitRate(
  hits: number | null | undefined,
  total: number | null | undefined,
): { pct: number; formula: string } | null {
  if (hits == null || total == null || total <= 0 || hits < 0 || hits > total) return null;
  return {
    pct: (hits / total) * 100,
    formula: `${hits} correct directional calls out of ${total} settled forecasts`,
  };
}

/** True when the rules-based gauge and the model disagree — surfaced, not hidden. */
export function signalsDisagree(
  gauge: "Buy" | "Neutral" | "Sell" | null,
  model: "BUY" | "HOLD" | "SELL" | null,
): boolean {
  if (!gauge || !model) return false;
  const normalisedGauge = gauge.toUpperCase();
  if (normalisedGauge === "NEUTRAL" && model === "HOLD") return false;
  return normalisedGauge !== model;
}
