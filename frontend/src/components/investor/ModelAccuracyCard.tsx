import type { FC } from "react";
import { useMemo } from "react";
import type { SnapshotDoc, PricePoint } from "../../types";

interface Props {
  /** Recent snapshots (newest first) — from useRecentSnapshots. */
  snapshots: SnapshotDoc[] | undefined;
  /** Full guarded price history from usePrices — used to look up the actual
   *  close on each snapshot's `next_trading_day` without extra RTDB fetches. */
  history: PricePoint[];
  /** How many scored calls to summarise. Defaults to 30 which is roughly
   *  a trading month — long enough to average out luck, short enough that
   *  a recent model change dominates the number. */
  window?: number;
}

interface ScoredCall {
  runDate: string;
  targetDate: string;
  signal: "BUY" | "HOLD" | "SELL";
  predicted: number;
  actual: number;
  currentAtCall: number;
  /** Direction the signal implied: +1 BUY, -1 SELL, 0 HOLD. */
  signalDir: number;
  /** Direction the actual move went: +1 up, -1 down, 0 flat. */
  actualDir: number;
  /** Prediction absolute % error vs actual. */
  mape: number;
}

function classifyDir(from: number, to: number): number {
  if (to > from * 1.001) return 1;
  if (to < from * 0.999) return -1;
  return 0;
}

/**
 * Renders a rolling hit-rate + MAPE summary of the model's recent calls.
 *
 * "Hit rate" = fraction of BUY/SELL calls where the actual direction
 * matched the signal. HOLD calls are excluded from hit rate — they claim
 * no direction so they can't be scored on direction.
 *
 * "MAPE" = mean absolute % error of predicted vs actual close on the
 * target day, across all scored calls (BUY/SELL/HOLD).
 *
 * A call is "scored" when we have both a snapshot AND the actual close
 * for its `next_trading_day` present in the RTDB history. Snapshots
 * whose target day hasn't happened yet, or whose target day is missing
 * from RTDB (thinly-traded ticker with no bar), are excluded.
 */
export const ModelAccuracyCard: FC<Props> = ({ snapshots, history, window = 30 }) => {
  const priceByDate = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of history) m.set(p.date, p.price);
    return m;
  }, [history]);

  const scored: ScoredCall[] = useMemo(() => {
    if (!snapshots) return [];
    const out: ScoredCall[] = [];
    for (const s of snapshots) {
      const target = s.next_trading_day;
      const actual = priceByDate.get(target);
      if (actual == null) continue;
      const cur = s.current_price_KES;
      const pred = s.predicted_price_KES;
      if (!Number.isFinite(cur) || cur <= 0) continue;
      if (!Number.isFinite(pred) || pred <= 0) continue;
      out.push({
        runDate: s.run_date,
        targetDate: target,
        signal: s.risk_adjusted_signal,
        predicted: pred,
        actual,
        currentAtCall: cur,
        signalDir: s.risk_adjusted_signal === "BUY" ? 1 : s.risk_adjusted_signal === "SELL" ? -1 : 0,
        actualDir: classifyDir(cur, actual),
        mape: Math.abs(actual - pred) / Math.max(actual, 1e-6) * 100,
      });
      if (out.length >= window) break;
    }
    return out;
  }, [snapshots, priceByDate, window]);

  if (!snapshots || snapshots.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface px-5 py-4">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Model Accuracy
        </p>
        <p className="mt-2 text-sm text-hint">
          No snapshots recorded yet — the accuracy panel populates after the
          daily inference has run and target days have elapsed.
        </p>
      </div>
    );
  }

  const directional = scored.filter(c => c.signal !== "HOLD");
  const hits = directional.filter(c => c.signalDir === c.actualDir);
  const hitRate = directional.length > 0
    ? Math.round((hits.length / directional.length) * 100)
    : null;
  const meanMape = scored.length > 0
    ? scored.reduce((a, c) => a + c.mape, 0) / scored.length
    : null;

  // Split hit-rate by signal so users see whether the model is stronger on
  // BUY vs SELL — often asymmetric on real financial data.
  const buys = directional.filter(c => c.signal === "BUY");
  const sells = directional.filter(c => c.signal === "SELL");
  const buyHits = buys.filter(c => c.actualDir >= 0).length;
  const sellHits = sells.filter(c => c.actualDir <= 0).length;
  const buyHitPct  = buys.length  > 0 ? Math.round(buyHits  / buys.length  * 100) : null;
  const sellHitPct = sells.length > 0 ? Math.round(sellHits / sells.length * 100) : null;

  const hitTone =
    hitRate == null ? "text-hint"
    : hitRate >= 60 ? "text-emerald-500"
    : hitRate >= 45 ? "text-amber-400"
    : "text-red-500";

  return (
    <div className="rounded-xl border border-rim bg-surface px-5 py-4 space-y-3">
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          Model Accuracy · last {scored.length} scored calls
        </p>
        {snapshots.length > scored.length && (
          <p className="text-[10px] text-hint">
            {snapshots.length - scored.length} pending / unscoreable
          </p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-seam bg-raised/40 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Direction Hit</p>
          <p className={`mt-1 font-mono text-2xl font-bold tabular-nums ${hitTone}`}>
            {hitRate != null ? `${hitRate}%` : "—"}
          </p>
          <p className="mt-0.5 text-[10px] text-hint">
            {directional.length > 0 ? `${hits.length}/${directional.length} directional calls` : "no BUY/SELL calls"}
          </p>
        </div>
        <div className="rounded-lg border border-seam bg-raised/40 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">MAPE</p>
          <p className="mt-1 font-mono text-2xl font-bold tabular-nums text-ink">
            {meanMape != null ? `${meanMape.toFixed(1)}%` : "—"}
          </p>
          <p className="mt-0.5 text-[10px] text-hint">avg |predicted − actual|</p>
        </div>
        <div className="rounded-lg border border-seam bg-raised/40 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">Split</p>
          <p className="mt-1 font-mono text-xs text-ink">
            BUY {buyHitPct  != null ? `${buyHitPct}%`  : "—"}
            <span className="ml-1 text-hint">({buys.length})</span>
          </p>
          <p className="mt-0.5 font-mono text-xs text-ink">
            SELL {sellHitPct != null ? `${sellHitPct}%` : "—"}
            <span className="ml-1 text-hint">({sells.length})</span>
          </p>
        </div>
      </div>

      {scored.length >= 5 && (
        <p className="text-[10px] leading-relaxed text-hint">
          A random directional coin-flip would score 50%. Rate ≥60% is meaningful;
          &lt;45% suggests the model is worse than flipping. Persistent low scores
          on one direction (e.g. BUY 30% / SELL 65%) mean the model works one way.
        </p>
      )}
    </div>
  );
};
