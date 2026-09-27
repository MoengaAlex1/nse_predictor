// Portfolio Builder — pure math layer.
//
// Every number that lands on-screen originates here or in the read hook.
// No LLM/AI invents any financial figure. All calls are deterministic
// and unit-tested (see portfolio.test.ts).
//
// The optimizer is a single-pass, explainable, sector-capped, weighted-
// score allocator (methodology chosen in the audit at Section 16):
//   1. Filter universe (drop SELL, missing horizon data, illiquid)
//   2. Fitness score = pct_return * direction_hit - λ * volatility
//      + small sector-diversify bonus. λ scales with the risk profile.
//   3. Sort desc, greedy-pick top-N subject to caps (max 2 per sector,
//      total sector <= 40%, per-stock 5–30%).
//   4. Weights proportional to (positive) fitness, floor-clipped and
//      normalised to sum to 1.
//   5. Correlation reweight: any pair with |ρ| > 0.7 forces 5pp shift
//      from the higher-vol holding to a lower-correlated runner-up.
//   6. Projection at horizon: normal-approx bands using portfolio σ
//      computed from weighted vols + correlation matrix. Conservative
//      = expected - 1.5σ, Optimistic = expected + 1.5σ.

export type RiskProfile = "conservative" | "balanced" | "growth";
export type HorizonKey = "1M" | "3M" | "6M" | "9M" | "12M";

export interface UniverseTicker {
  ticker: string;
  name: string;
  sector: string;
  signal: "BUY" | "HOLD" | "SELL" | null;
  currentPrice: number | null;
  volatility30d: number | null;    // percent, annualised is separate
  avgVolume30d: number | null;
  radarScore: number | null;       // 0..30 total from RadarScoreCard (5 axes × 6)
  radarDenominator: number;        // out of what — usually 30, less if some axes are n/a
  dividendYield: number | null;    // trailing 12M %, may be null
  // Per-horizon prediction from the multi-horizon LightGBM model.
  // Null when the model hasn't trained on this ticker (fresh listing).
  horizonPredictions: Partial<Record<HorizonKey, HorizonPrediction>>;
}

export interface HorizonPrediction {
  horizonDays: number;
  pctReturn: number;              // percent, signed
  targetPrice: number | null;
  mape: number | null;            // percentage points
  directionHit: number | null;    // 0..1
}

export interface Holding {
  ticker: string;
  name: string;
  sector: string;
  weight: number;                 // 0..1
  allocationKes: number;
  shares: number;                 // floored — NSE has no fractionals
  cashResidueKes: number;         // amount that couldn't buy a whole share
  currentPrice: number;
  reasons: string[];              // built from real metrics — see explainHolding
}

export interface PortfolioMetrics {
  expectedReturnPct: number;               // weighted horizon return
  expectedValueKes: number;
  conservativeValueKes: number;
  optimisticValueKes: number;
  portfolioSigmaPct: number;               // annualised-scale portfolio σ
  riskBand: "Low" | "Moderate" | "High";
  diversification: {
    hhi: number;                           // 0..1, lower = more diverse
    sectorCount: number;
    avgPairwiseCorr: number | null;
    score: "Poor" | "Fair" | "Good";
  };
  riskDrivers: string[];                   // human-readable
}

export interface BuildInputs {
  amountKes: number;
  horizon: HorizonKey;
  risk: RiskProfile;
  universe: UniverseTicker[];
  correlation?: Record<string, Record<string, number>>;
  /** Number of holdings target (default 5). Caller can override for
   *  concentrated / diversified sub-modes later. */
  targetHoldings?: number;
}

// ─── Constants ──────────────────────────────────────────────────────────────

const RISK_LAMBDA: Record<RiskProfile, number> = {
  // λ multiplies the volatility penalty in the fitness score. Higher λ
  // means "avoid volatile names even if they have good expected return".
  conservative: 2.0,
  balanced:     1.0,
  growth:       0.5,
};

const RISK_HOLDING_CAP: Record<RiskProfile, number> = {
  conservative: 0.25,   // no single name > 25%
  balanced:     0.30,
  growth:       0.35,
};

const MIN_HOLDING = 0.05;         // 5% floor — anything smaller is noise
const MAX_SECTOR_TOTAL = 0.40;
const MAX_PER_SECTOR = 2;
const MIN_LIQUIDITY_KES = 500_000; // per day, price × avg_volume_30d
const CORRELATION_PENALTY_THRESHOLD = 0.7;

const HORIZON_TRADING_DAYS: Record<HorizonKey, number> = {
  "1M": 21, "3M": 63, "6M": 126, "9M": 189, "12M": 252,
};

// ─── Public API ─────────────────────────────────────────────────────────────

/**
 * Build a recommended portfolio from the universe. Deterministic given
 * the same inputs — every allocation is traceable to a metric.
 *
 * Returns holdings + a diagnostic array of tickers that were dropped
 * and why, so the "why not X?" story can be surfaced in the UI.
 */
export function buildPortfolio(inputs: BuildInputs): { holdings: Holding[]; excluded: Array<{ ticker: string; reason: string }> } {
  const { amountKes, horizon, risk, universe, correlation, targetHoldings = 5 } = inputs;
  const lambda = RISK_LAMBDA[risk];
  const perStockCap = RISK_HOLDING_CAP[risk];

  const excluded: Array<{ ticker: string; reason: string }> = [];
  const eligible: Array<{ t: UniverseTicker; pred: HorizonPrediction; fitness: number }> = [];

  for (const t of universe) {
    if (t.signal === "SELL") { excluded.push({ ticker: t.ticker, reason: "SELL signal" }); continue; }
    const pred = t.horizonPredictions[horizon];
    if (!pred) { excluded.push({ ticker: t.ticker, reason: `no ${horizon} prediction` }); continue; }
    if (t.volatility30d == null || t.currentPrice == null) {
      excluded.push({ ticker: t.ticker, reason: "missing volatility or price" }); continue;
    }
    const dailyValue = (t.avgVolume30d ?? 0) * t.currentPrice;
    if (dailyValue < MIN_LIQUIDITY_KES) {
      excluded.push({ ticker: t.ticker, reason: `illiquid (KES ${Math.round(dailyValue / 1000)}k/day)` });
      continue;
    }

    // Fitness = expected return × how often the model gets direction right
    // - volatility penalty. Direction hit is treated as a discount factor
    // (0..1) so a 5% predicted return with 60% direction hit beats a 10%
    // predicted return with 20% direction hit.
    const dirHit = pred.directionHit ?? 0.5;      // no backtest → neutral
    const fitness = pred.pctReturn * dirHit - lambda * t.volatility30d;
    eligible.push({ t, pred, fitness });
  }

  // Sort by fitness desc, then greedy-pick with sector caps.
  eligible.sort((a, b) => b.fitness - a.fitness);

  const sectorCount: Map<string, number> = new Map();
  const picked: typeof eligible = [];
  for (const cand of eligible) {
    const sec = cand.t.sector || "Uncategorised";
    if ((sectorCount.get(sec) ?? 0) >= MAX_PER_SECTOR) {
      excluded.push({ ticker: cand.t.ticker, reason: `sector cap (${sec} already has ${MAX_PER_SECTOR})` });
      continue;
    }
    picked.push(cand);
    sectorCount.set(sec, (sectorCount.get(sec) ?? 0) + 1);
    if (picked.length >= targetHoldings) break;
  }

  if (picked.length === 0) {
    return { holdings: [], excluded };
  }

  // Weight ∝ fitness (shifted so the lowest is at least 1 — avoids
  // negative weights when a picked holding has slightly negative fitness).
  const minF = Math.min(...picked.map(p => p.fitness));
  const shift = minF < 1 ? 1 - minF : 0;
  const rawWeights = picked.map(p => p.fitness + shift);
  let weights = normalise(rawWeights);

  // Enforce per-stock cap. Clip and re-normalise until stable.
  weights = enforceCap(weights, perStockCap);
  // Enforce sector-total cap. Same clip-and-normalise idea, grouped.
  weights = enforceSectorCap(weights, picked.map(p => p.t.sector), MAX_SECTOR_TOTAL);
  // Floor tiny slivers to 0 and re-normalise. Below MIN_HOLDING isn't
  // meaningful and just clutters the UI.
  weights = floorAndNormalise(weights, MIN_HOLDING);

  // Correlation reweight. If any pair has |ρ| > 0.7, shift 5pp from the
  // higher-vol side to the lowest-correlation holding.
  if (correlation) {
    weights = correlationReweight(weights, picked.map(p => p.t), correlation);
  }

  // Zip into Holding[] with real share counts + KES amounts.
  const holdings: Holding[] = picked
    .map((p, i) => {
      const alloc = weights[i] * amountKes;
      const shares = Math.floor(alloc / p.t.currentPrice!);
      const actualCost = shares * p.t.currentPrice!;
      return {
        ticker: p.t.ticker,
        name: p.t.name,
        sector: p.t.sector || "Uncategorised",
        weight: weights[i],
        allocationKes: alloc,
        shares,
        cashResidueKes: alloc - actualCost,
        currentPrice: p.t.currentPrice!,
        reasons: explainHolding(p.t, p.pred, p.fitness, weights[i], risk),
      };
    })
    .filter(h => h.weight > 0);

  return { holdings, excluded };
}

/**
 * Portfolio metrics — expected return, projected value bands, portfolio
 * σ, risk band + drivers, diversification.
 *
 * All bands are ±1.5σ around the expected value (chosen at audit-time).
 * σ built from per-holding volatility + optional correlation matrix.
 * No correlation → assumes 0.3 avg pairwise (a conservative default
 * for equity portfolios in a single market).
 */
export function computeMetrics(
  holdings: Holding[],
  horizon: HorizonKey,
  universe: UniverseTicker[],
  amountKes: number,
  correlation?: Record<string, Record<string, number>>,
): PortfolioMetrics {
  if (holdings.length === 0) return emptyMetrics(amountKes);
  const byTicker = new Map(universe.map(u => [u.ticker, u]));

  // Weighted expected return over the horizon.
  let expectedReturnPct = 0;
  for (const h of holdings) {
    const u = byTicker.get(h.ticker);
    const pred = u?.horizonPredictions[horizon];
    if (!pred) continue;
    expectedReturnPct += h.weight * pred.pctReturn;
  }

  // Portfolio variance. Scale daily volatility to the horizon via
  // sqrt(trading_days) — standard Wiener scaling.
  const daysScale = Math.sqrt(HORIZON_TRADING_DAYS[horizon]);
  const sigmas: number[] = holdings.map(h => {
    const v = byTicker.get(h.ticker)?.volatility30d ?? 0;
    return v * daysScale;
  });
  const { portfolioSigma, avgCorr } = portfolioSigmaFromCorr(
    holdings.map(h => h.weight),
    sigmas,
    holdings.map(h => h.ticker),
    correlation,
  );

  const expectedValueKes = amountKes * (1 + expectedReturnPct / 100);
  const bandKes = amountKes * (portfolioSigma / 100) * 1.5;
  const conservativeValueKes = Math.max(0, expectedValueKes - bandKes);
  const optimisticValueKes = expectedValueKes + bandKes;

  // Risk band from annualised portfolio σ. Cut-offs from Section 18.
  // portfolioSigma is already horizon-scaled; convert to annualised
  // for the band cut-off (divide by sqrt(daysScale)^2 · 252/days? no —
  // just re-scale: annualised = daily_sigma * sqrt(252) = portfolioSigma
  // * sqrt(252/horizon_days)).
  const annualisedSigma = portfolioSigma * Math.sqrt(252 / HORIZON_TRADING_DAYS[horizon]);
  const riskBand: PortfolioMetrics["riskBand"] =
    annualisedSigma < 15 ? "Low" :
    annualisedSigma < 30 ? "Moderate" : "High";

  // Diversification score.
  const hhi = holdings.reduce((s, h) => s + h.weight * h.weight, 0);
  const sectors = new Set(holdings.map(h => h.sector));
  const divScore: "Poor" | "Fair" | "Good" =
    hhi < 0.22 && sectors.size >= 4 ? "Good" :
    hhi < 0.35 && sectors.size >= 3 ? "Fair" : "Poor";

  // Risk drivers — every entry references a real metric so the tooltip
  // can be built from it. Order = most-actionable first.
  const drivers: string[] = [];
  const topHolding = [...holdings].sort((a, b) => b.weight - a.weight)[0];
  if (topHolding && topHolding.weight > 0.25) {
    drivers.push(`Concentrated in ${topHolding.ticker} (${(topHolding.weight * 100).toFixed(0)}% of portfolio)`);
  }
  const sectorTotals = new Map<string, number>();
  holdings.forEach(h => sectorTotals.set(h.sector, (sectorTotals.get(h.sector) ?? 0) + h.weight));
  const topSector = [...sectorTotals.entries()].sort(([, a], [, b]) => b - a)[0];
  if (topSector && topSector[1] > 0.40) {
    drivers.push(`${topSector[0]} sector at ${(topSector[1] * 100).toFixed(0)}% — sector-specific shocks would hit this portfolio harder`);
  }
  if (annualisedSigma > 25) {
    drivers.push(`Annualised volatility ${annualisedSigma.toFixed(0)}% — expect daily swings; band is ±${bandKes.toLocaleString("en-KE", { maximumFractionDigits: 0 })} at the horizon`);
  }
  if (avgCorr != null && avgCorr > 0.5) {
    drivers.push(`Holdings are highly correlated (avg ρ = ${avgCorr.toFixed(2)}) — diversification benefit is limited`);
  }
  if (HORIZON_TRADING_DAYS[horizon] <= 21 && holdings.some(h => (byTicker.get(h.ticker)?.horizonPredictions[horizon]?.directionHit ?? 0.5) < 0.55)) {
    drivers.push("Short horizon (1M) — model direction hit rate is near coin-flip; treat the target as low-confidence");
  }

  return {
    expectedReturnPct,
    expectedValueKes,
    conservativeValueKes,
    optimisticValueKes,
    portfolioSigmaPct: portfolioSigma,
    riskBand,
    diversification: {
      hhi,
      sectorCount: sectors.size,
      avgPairwiseCorr: avgCorr,
      score: divScore,
    },
    riskDrivers: drivers,
  };
}

// ─── Internal helpers ───────────────────────────────────────────────────────

function normalise(xs: number[]): number[] {
  const s = xs.reduce((a, b) => a + b, 0);
  if (s === 0) return xs.map(() => 1 / xs.length);
  return xs.map(x => x / s);
}

function enforceCap(weights: number[], cap: number): number[] {
  // Iterative clip-and-redistribute. Terminates because each pass either
  // reduces the max weight or leaves everything at ≤ cap.
  for (let pass = 0; pass < 20; pass += 1) {
    const over = weights.map(w => Math.max(0, w - cap));
    const excess = over.reduce((a, b) => a + b, 0);
    if (excess < 1e-6) return weights;
    const clipped = weights.map(w => Math.min(w, cap));
    const roomTotal = clipped.reduce((a, w) => a + Math.max(0, cap - w), 0);
    if (roomTotal < 1e-6) return clipped;   // everyone capped — shouldn't happen if cap × N ≥ 1
    // Redistribute the clipped excess proportionally to the remaining
    // headroom of holdings that aren't yet at cap.
    weights = clipped.map(w => w < cap
      ? w + (excess * ((cap - w) / roomTotal))
      : w);
  }
  return weights;
}

function enforceSectorCap(weights: number[], sectors: string[], cap: number): number[] {
  const sectorTotals = new Map<string, number>();
  weights.forEach((w, i) => sectorTotals.set(sectors[i], (sectorTotals.get(sectors[i]) ?? 0) + w));
  let over = 0;
  for (const [, t] of sectorTotals) over += Math.max(0, t - cap);
  if (over < 1e-6) return weights;

  // For each over-cap sector, scale its members down so the sector
  // totals `cap`, then redistribute the excess proportionally to the
  // under-cap sectors' members.
  const out = weights.slice();
  const donors: number[] = [];
  const receivers: number[] = [];
  sectorTotals.forEach((total, sec) => {
    if (total > cap) donors.push(...weights.map((_, i) => i).filter(i => sectors[i] === sec));
    else receivers.push(...weights.map((_, i) => i).filter(i => sectors[i] === sec));
  });
  // Scale donors down.
  for (const [sec, total] of sectorTotals) {
    if (total <= cap) continue;
    const scale = cap / total;
    weights.forEach((w, i) => {
      if (sectors[i] === sec) out[i] = w * scale;
    });
  }
  const removed = weights.reduce((s, w) => s + w, 0) - out.reduce((s, w) => s + w, 0);
  if (receivers.length && removed > 0) {
    const recvSum = receivers.reduce((s, i) => s + out[i], 0);
    if (recvSum > 0) {
      for (const i of receivers) out[i] += removed * (out[i] / recvSum);
    }
  }
  return out;
}

function floorAndNormalise(weights: number[], minW: number): number[] {
  const flagged = weights.map(w => (w < minW ? 0 : w));
  if (flagged.every(w => w === 0)) return normalise(weights);
  return normalise(flagged);
}

function correlationReweight(
  weights: number[],
  tickers: UniverseTicker[],
  corr: Record<string, Record<string, number>>,
): number[] {
  const out = weights.slice();
  const shift = 0.05;   // 5pp
  for (let i = 0; i < tickers.length; i += 1) {
    for (let j = i + 1; j < tickers.length; j += 1) {
      const r = corr[tickers[i].ticker]?.[tickers[j].ticker];
      if (r == null || Math.abs(r) <= CORRELATION_PENALTY_THRESHOLD) continue;
      // Higher-vol side loses 5pp to the lowest-corr holding.
      const iVol = tickers[i].volatility30d ?? 0;
      const jVol = tickers[j].volatility30d ?? 0;
      const [loser] = iVol >= jVol ? [i] : [j];
      // Find the lowest avg-|ρ| holding (other than loser) to receive.
      let bestReceiver = -1;
      let bestScore = Infinity;
      for (let k = 0; k < tickers.length; k += 1) {
        if (k === loser) continue;
        const row = corr[tickers[k].ticker] || {};
        const avg = tickers.reduce((s, t, idx) => {
          if (idx === k) return s;
          return s + Math.abs(row[t.ticker] ?? 0);
        }, 0) / Math.max(1, tickers.length - 1);
        if (avg < bestScore) { bestScore = avg; bestReceiver = k; }
      }
      if (bestReceiver >= 0 && out[loser] > shift) {
        out[loser] -= shift;
        out[bestReceiver] += shift;
      }
    }
  }
  return normalise(out);
}

function portfolioSigmaFromCorr(
  weights: number[],
  sigmas: number[],
  tickers: string[],
  corr?: Record<string, Record<string, number>>,
): { portfolioSigma: number; avgCorr: number | null } {
  const n = weights.length;
  let variance = 0;
  let pairCount = 0;
  let corrSum = 0;
  for (let i = 0; i < n; i += 1) {
    for (let j = 0; j < n; j += 1) {
      const w_i = weights[i];
      const w_j = weights[j];
      const s_i = sigmas[i];
      const s_j = sigmas[j];
      let r: number;
      if (i === j) {
        r = 1;
      } else {
        const found = corr?.[tickers[i]]?.[tickers[j]];
        if (found != null) {
          r = found;
          corrSum += found;
          pairCount += 1;
        } else {
          // Prior when correlation missing: 0.3, a conservative default
          // for two Kenyan-market equities. Documented in the audit.
          r = 0.3;
        }
      }
      variance += w_i * w_j * s_i * s_j * r;
    }
  }
  return {
    portfolioSigma: Math.sqrt(Math.max(0, variance)),
    avgCorr: pairCount > 0 ? corrSum / pairCount : null,
  };
}

function explainHolding(
  t: UniverseTicker,
  pred: HorizonPrediction,
  fitness: number,
  weight: number,
  risk: RiskProfile,
): string[] {
  const parts: string[] = [];
  parts.push(
    `${(weight * 100).toFixed(0)}% allocated — ${t.ticker} shows a ${pred.pctReturn >= 0 ? "+" : ""}${pred.pctReturn.toFixed(1)}% model target${pred.directionHit != null ? ` with ${(pred.directionHit * 100).toFixed(0)}% direction-hit accuracy on the backtest` : ""}.`,
  );
  if (t.signal) parts.push(`Current AI signal: ${t.signal}.`);
  if (t.volatility30d != null) {
    const isCalm = t.volatility30d < 1.5;
    parts.push(`30-day daily volatility ${t.volatility30d.toFixed(1)}% — ${isCalm ? `low for the ${risk} bucket` : "on the higher end; sized accordingly"}.`);
  }
  if (t.radarScore != null && t.radarDenominator > 0) parts.push(`Fundamental score ${t.radarScore.toFixed(0)}/${t.radarDenominator}.`);
  if (t.dividendYield != null && t.dividendYield > 0.5) parts.push(`Trailing dividend yield ${t.dividendYield.toFixed(1)}% adds income.`);
  parts.push(`Adds ${t.sector} sector exposure. Overall fitness ${fitness.toFixed(2)}.`);
  return parts;
}

function emptyMetrics(amountKes: number): PortfolioMetrics {
  return {
    expectedReturnPct: 0,
    expectedValueKes: amountKes,
    conservativeValueKes: amountKes,
    optimisticValueKes: amountKes,
    portfolioSigmaPct: 0,
    riskBand: "Low",
    diversification: { hhi: 0, sectorCount: 0, avgPairwiseCorr: null, score: "Poor" },
    riskDrivers: ["No eligible tickers matched the filter — try relaxing risk or extending the horizon."],
  };
}
