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

// Phase 5 scaffolding — non-equity asset classes.
// Everything downstream treats a Holding as a positive-weight equity
// position, but the shape is deliberately generic. When we add ETFs
// (fund_of_funds), bonds (yield-plus-duration), or money-market funds
// (fixed-yield), each new type declares its own AssetClass tag and
// provides its own expected-return + volatility helper. The optimiser
// stays generic — score = expectedReturn * confidence - λ * volatility
// — so adding a class is: (1) add a case here, (2) add its data source
// to UniverseTicker, (3) plug in a per-class return/vol function.
// See docs/PORTFOLIO_BUILDER_ROADMAP.md for the sequenced plan.
export type AssetClass = "equity" | "etf" | "bond" | "mmf";

export interface UniverseTicker {
  ticker: string;
  name: string;
  sector: string;
  signal: "BUY" | "HOLD" | "SELL" | null;
  currentPrice: number | null;
  volatility30d: number | null;    // daily stdev × 100 (matches technicals doc)
  avgVolume30d: number | null;
  radarScore: number | null;       // 0..30 total from RadarScoreCard (5 axes × 6)
  radarDenominator: number;        // out of what — usually 30, less if some axes are n/a
  dividendYield: number | null;    // trailing 12M %, may be null
  // Per-horizon prediction from the multi-horizon LightGBM model.
  // Null when the model hasn't trained on this ticker (fresh listing).
  horizonPredictions: Partial<Record<HorizonKey, HorizonPrediction>>;

  // Multi-factor signals used by the enhanced fitness function. Every
  // field is null-safe — a missing factor simply drops out of the
  // weighted sum rather than penalising the ticker. All values are
  // sourced from data the platform already computes:
  //  momentum:  trailing return % over the given window from price_history
  //  rsi14:     technicals doc
  //  macdSignal: sign of macd_hist (+1 bullish / -1 bearish / 0 flat)
  //  adx14:     trend strength from technicals
  //  peRatio:   currentPrice / latest_positive_eps (annual)
  momentum1m: number | null;
  momentum3m: number | null;
  momentum6m: number | null;
  rsi14: number | null;
  macdSignal: -1 | 0 | 1 | null;
  adx14: number | null;
  peRatio: number | null;

  // Phase 5 — defaults to "equity" so existing callers keep working
  // without a required update. ETFs / bonds / MMFs will flip this and
  // pull their return/vol from a different source (bond yield curves,
  // fund NAVs). See docs/PORTFOLIO_BUILDER_ROADMAP.md.
  assetClass?: AssetClass;
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
  breakdown?: FitnessBreakdown;   // internal — surfaced in "Why?" cards
  /** Position size as a fraction of the ticker's average daily traded
   *  value. Above ~5% suggests execution would move the price against
   *  the buyer — surfaced in the risk drivers when it kicks in. */
  liquidityLoad?: number;
}

export interface PortfolioMetrics {
  expectedReturnPct: number;               // weighted horizon return
  expectedValueKes: number;
  conservativeValueKes: number;
  optimisticValueKes: number;
  portfolioSigmaPct: number;               // horizon-scaled portfolio σ (percent)
  weightedMapePP: number;                  // weighted per-horizon MAPE (pp) — model's own uncertainty
  sharpeRatio: number | null;              // (expectedReturn - riskFree) / σ, both horizon-scaled
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

// Diagnostic view of how a single ticker's fitness score was assembled.
// Attached to each Holding so the "why" explanation can cite the
// factors that actually drove selection (not hand-written text).
export interface FitnessBreakdown {
  returnFactor: number;
  momentumFactor: number;
  trendFactor: number;
  qualityFactor: number;
  valueFactor: number;
  yieldFactor: number;
  volPenalty: number;
  rawFitness: number;   // pre-vol-penalty
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

// Per-horizon factor weights. Rationale:
//  - Short horizons (1M, 3M): momentum + model return dominate; earnings
//    haven't cycled yet, so fundamental quality/value have less time to
//    matter than the current technical setup.
//  - Long horizons (6M+): fundamentals (quality, value, yield) get the
//    weight back because a full earnings cycle happens; momentum decays
//    to near-zero because 6-12 month reversion is well-documented in the
//    academic literature (Jegadeesh 1990, Fama-French).
//  - `return` is the LightGBM point estimate — the direct model output.
//    Confidence scale (1 - MAPE/30) discounts noisy horizons.
//  - `trend` = RSI/MACD/ADX composite; short-term momentum quality.
// Weights sum to 1 per horizon so the linear combination stays on the
// same scale as any single factor.
const HORIZON_WEIGHTS: Record<HorizonKey, {
  return: number; momentum: number; trend: number; quality: number; value: number; yield: number;
}> = {
  "1M":  { return: 0.30, momentum: 0.30, trend: 0.20, quality: 0.10, value: 0.05, yield: 0.05 },
  "3M":  { return: 0.35, momentum: 0.20, trend: 0.15, quality: 0.15, value: 0.10, yield: 0.05 },
  "6M":  { return: 0.30, momentum: 0.10, trend: 0.10, quality: 0.25, value: 0.15, yield: 0.10 },
  "9M":  { return: 0.25, momentum: 0.05, trend: 0.05, quality: 0.30, value: 0.20, yield: 0.15 },
  "12M": { return: 0.20, momentum: 0.05, trend: 0.05, quality: 0.30, value: 0.20, yield: 0.20 },
};

// Sector-median trailing P/E used for the value factor. Source: audit
// section 4 — same table already in RadarScoreCard, extracted here to
// avoid depending on the UI component. Missing sector → value factor
// simply drops out.
const SECTOR_MEDIAN_PE: Record<string, number> = {
  Banking: 7.8,
  Insurance: 6.2,
  "Manufacturing and Allied": 11.4,
  "Telecommunication and Technology": 18.5,
  "Energy and Petroleum": 9.1,
  "Commercial and Services": 13.2,
  Agricultural: 14.1,
  Investment: 8.9,
  "Real Estate Investment Trust": 22.0,
  "Automobiles and Accessories": 10.5,
  "Construction and Allied": 9.8,
};

// Position-size penalty: if the intended allocation is > this fraction of
// a name's typical daily traded value, the trade will move the price
// against you. Standard trading assumption; well-known impact-cost model
// families (Almgren–Chriss) show cost grows super-linearly past ~10-15%
// of ADV. We use 5% as the "no penalty" band since NSE liquidity is
// generally thin. Penalty grows quadratically past that.
const LIQUIDITY_IMPACT_CAP = 0.05;

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
  // Base cap; adaptive widening happens AFTER we know how many
  // candidates actually pass the filter (see near enforceCap call).
  const baseCap = RISK_HOLDING_CAP[risk];

  const excluded: Array<{ ticker: string; reason: string }> = [];
  const eligible: Array<{ t: UniverseTicker; pred: HorizonPrediction; fitness: number; breakdown: FitnessBreakdown }> = [];
  const horizonWeights = HORIZON_WEIGHTS[horizon];
  const horizonDays = HORIZON_TRADING_DAYS[horizon];

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

    // ── Multi-factor fitness ─────────────────────────────────────────────
    // Every factor is normalised to a roughly comparable 0-15 scale (a
    // 15% signal is the "big" case). Horizon weights then linearly combine.
    // Any factor whose input is null contributes 0 (not penalised).

    // Factor 1: Model return, discounted by walk-forward confidence.
    // Confidence = 1 - min(1, mape / 30). MAPE ≥ 30pp → 0 confidence.
    // Direction hit adds a tie-breaker: a horizon where the model gets
    // sign right often is worth more than one where it flips.
    const confidence = 1 - Math.min(1, (pred.mape ?? 30) / 30);
    const dirHit = pred.directionHit ?? 0.5;
    const returnFactor = pred.pctReturn * confidence * (0.5 + dirHit);   // scaled so 0.5 hit ≈ neutral

    // Factor 2: Price momentum aligned with the horizon.
    // Short horizons care about 1M momentum; long horizons about 6M.
    // (Cross-sectional momentum literature: Jegadeesh & Titman 1993,
    // Fama & French 1996. Kenyan-market equivalent hasn't been peer-
    // reviewed but the same 3-12 month persistence shows in local data.)
    const momentumInput =
      horizonDays <= 30  ? (t.momentum1m ?? 0) :
      horizonDays <= 90  ? (t.momentum3m ?? t.momentum1m ?? 0) :
                            (t.momentum6m ?? t.momentum3m ?? 0);
    const momentumFactor = momentumInput;

    // Factor 3: Technical trend quality. ADX > 25 = strong trend; MACD
    // sign gives direction. Product gives a signed "trend strength" 0-2.
    const trendMag = Math.min(1, (t.adx14 ?? 0) / 50);
    const trendFactor = (t.macdSignal ?? 0) * trendMag * 15;   // scale to 0-15

    // Factor 4: Fundamental quality — Radar score normalised 0-1 × 15.
    const qualityFactor = t.radarScore != null && t.radarDenominator > 0
      ? (t.radarScore / t.radarDenominator) * 15
      : 0;

    // Factor 5: Value — sector-median-relative P/E. If PE is 30% below
    // the sector median → +4.5. If 30% above → −4.5. Cap at ±10.
    const sectorPe = SECTOR_MEDIAN_PE[t.sector];
    const valueFactor = (t.peRatio && sectorPe && t.peRatio > 0)
      ? Math.max(-10, Math.min(10, (1 - t.peRatio / sectorPe) * 15))
      : 0;

    // Factor 6: Dividend yield income contribution. Only matters at
    // longer horizons per the weights table.
    const yieldFactor = (t.dividendYield ?? 0);

    const rawFitness =
        horizonWeights.return   * returnFactor
      + horizonWeights.momentum * momentumFactor
      + horizonWeights.trend    * trendFactor
      + horizonWeights.quality  * qualityFactor
      + horizonWeights.value    * valueFactor
      + horizonWeights.yield    * yieldFactor;

    // Volatility penalty scaled to the horizon (variance grows linearly
    // with time; std with sqrt). Longer horizons "absorb" volatility
    // better, so the penalty per-day is horizon-invariant but the
    // effective σ over the horizon isn't. λ tightens for
    // conservative profiles.
    const volPenalty = lambda * (t.volatility30d ?? 0) * Math.sqrt(21 / Math.max(21, horizonDays));

    const fitness = rawFitness - volPenalty;

    eligible.push({
      t, pred, fitness,
      breakdown: { returnFactor, momentumFactor, trendFactor, qualityFactor, valueFactor, yieldFactor, volPenalty, rawFitness },
    });
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

  // Adaptive per-stock cap. When the eligible pool is small the base
  // cap can become a straitjacket — 3 picks × 30% = 90%, and the
  // follow-on normalisation would then flatten all weights to 33.3%
  // each, masking real fitness differences. Widen the cap enough that
  // N × cap ≥ 1.05, keeping the base cap as the lower bound for large
  // pools. This is what makes the recommendation stay differentiated
  // even when only a handful of tickers survive the filter.
  const perStockCap = Math.max(baseCap, 1.05 / picked.length);
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

  // Amount-sensitive re-weighting. For each candidate, compute how much
  // of one day's traded value the intended position would consume. If
  // it's over LIQUIDITY_IMPACT_CAP (5%), penalise proportionally and
  // shift the excess weight to whichever candidate has the most
  // liquidity headroom. This is what makes the recommendation react to
  // the user's KES amount — a KES 100k portfolio has no liquidity
  // pressure; a KES 10M one does.
  weights = liquidityAdjust(weights, picked.map(p => p.t), amountKes);

  // Zip into Holding[] with real share counts + KES amounts.
  const holdings: Holding[] = picked
    .map((p, i) => {
      const alloc = weights[i] * amountKes;
      const shares = Math.floor(alloc / p.t.currentPrice!);
      const actualCost = shares * p.t.currentPrice!;
      const dailyValue = (p.t.avgVolume30d ?? 0) * (p.t.currentPrice ?? 0);
      const liquidityLoad = dailyValue > 0 ? alloc / dailyValue : 0;
      return {
        ticker: p.t.ticker,
        name: p.t.name,
        sector: p.t.sector || "Uncategorised",
        weight: weights[i],
        allocationKes: alloc,
        shares,
        cashResidueKes: alloc - actualCost,
        currentPrice: p.t.currentPrice!,
        reasons: explainHolding(p.t, p.pred, p.fitness, weights[i], risk, p.breakdown, horizon, liquidityLoad),
        breakdown: p.breakdown,
        liquidityLoad,
      };
    })
    .filter(h => h.weight > 0);

  return { holdings, excluded };
}

function liquidityAdjust(
  weights: number[],
  tickers: UniverseTicker[],
  amountKes: number,
): number[] {
  // Positions that consume > cap of one day's traded value get scaled
  // down; the shortfall is redistributed to the candidate with the
  // most headroom. Iterate once — cascading edge cases (all candidates
  // over cap) are rare at Kenyan-market thin liquidity and would leave
  // an unfilled residue that manifests as < 100% invested.
  const dailyValue = tickers.map(t => (t.avgVolume30d ?? 0) * (t.currentPrice ?? 0));
  if (dailyValue.every(dv => dv <= 0)) return weights;
  const positionKes = weights.map(w => w * amountKes);
  const load = positionKes.map((p, i) => dailyValue[i] > 0 ? p / dailyValue[i] : 0);
  const overs = load.map(l => Math.max(0, l - LIQUIDITY_IMPACT_CAP));
  if (overs.every(o => o === 0)) return weights;

  const out = weights.slice();
  // Cap each over-weight position at LIQUIDITY_IMPACT_CAP × dailyValue.
  let excess = 0;
  for (let i = 0; i < out.length; i += 1) {
    if (load[i] > LIQUIDITY_IMPACT_CAP && dailyValue[i] > 0) {
      const cappedKes = LIQUIDITY_IMPACT_CAP * dailyValue[i];
      excess += out[i] * amountKes - cappedKes;
      out[i] = cappedKes / amountKes;
    }
  }
  // Redistribute to candidates with headroom, proportional to remaining
  // headroom (biggest daily-value gets most of it).
  const headroom = tickers.map((_, i) =>
    Math.max(0, LIQUIDITY_IMPACT_CAP * dailyValue[i] - out[i] * amountKes),
  );
  const headroomTotal = headroom.reduce((a, b) => a + b, 0);
  if (headroomTotal > 0 && excess > 0) {
    for (let i = 0; i < out.length; i += 1) {
      out[i] += (excess * headroom[i] / headroomTotal) / amountKes;
    }
  }
  return normalise(out);
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

  // Bands driven by the model's OWN uncertainty per horizon. MAPE is
  // the mean absolute error in percentage points on the horizon return,
  // measured on unseen recent history via walk-forward validation. This
  // is more honest than pure ±1.5σ from price volatility because a
  // ticker can be low-vol AND have a wildly-off model (or the reverse).
  // We combine:
  //   modelBand      = weighted MAPE × 1.5  (per-holding model error,
  //                     assumed independent across holdings so it's
  //                     already partially diversified — hence weighted
  //                     avg not sqrt sum)
  //   priceBand      = portfolio σ × 1.5    (co-movement from price vol
  //                     + correlation matrix — reflects real-world
  //                     diversification benefit).
  //   Combined       = sqrt(modelBand² + priceBand²)   (independent
  //                     sources of uncertainty).
  let weightedMape = 0;
  for (const h of holdings) {
    const pred = byTicker.get(h.ticker)?.horizonPredictions[horizon];
    if (pred?.mape != null) weightedMape += h.weight * pred.mape;
  }
  const modelBand = weightedMape * 1.5;
  const priceBand = portfolioSigma * 1.5;
  const combinedBandPct = Math.sqrt(modelBand * modelBand + priceBand * priceBand);
  const bandKes = amountKes * combinedBandPct / 100;
  const conservativeValueKes = Math.max(0, expectedValueKes - bandKes);
  const optimisticValueKes = expectedValueKes + bandKes;

  // Sharpe ratio using Kenya money-market rate (~10%/yr = ~0.04%/day)
  // as the risk-free proxy. Scaled to the horizon so it's directly
  // comparable to the horizon expected return.
  const riskFreeHorizon = 10 * (HORIZON_TRADING_DAYS[horizon] / 252);
  const sharpeRatio = portfolioSigma > 0
    ? (expectedReturnPct - riskFreeHorizon) / portfolioSigma
    : null;

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
  // Liquidity load — surfaced when any holding is above the 5% ADV cap.
  const heavyLoad = holdings.find(h => (h.liquidityLoad ?? 0) > LIQUIDITY_IMPACT_CAP);
  if (heavyLoad) {
    drivers.push(`${heavyLoad.ticker} allocation is ${((heavyLoad.liquidityLoad ?? 0) * 100).toFixed(1)}% of one day's traded value — execution slippage risk`);
  }
  // Weighted MAPE — flag when the model itself is uncertain at this horizon.
  if (weightedMape > 15) {
    drivers.push(`Model uncertainty at ${horizon} is ${weightedMape.toFixed(0)}pp on average — projections are wide by design`);
  }

  return {
    expectedReturnPct,
    expectedValueKes,
    conservativeValueKes,
    optimisticValueKes,
    portfolioSigmaPct: portfolioSigma,
    weightedMapePP: weightedMape,
    sharpeRatio,
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
  breakdown: FitnessBreakdown | undefined,
  horizon: HorizonKey,
  liquidityLoad: number,
): string[] {
  const parts: string[] = [];
  const returnPart = pred.mape != null
    ? `${(weight * 100).toFixed(0)}% — model projects ${pred.pctReturn >= 0 ? "+" : ""}${pred.pctReturn.toFixed(1)}% at ${horizon} (backtest MAPE ±${pred.mape.toFixed(1)}pp${pred.directionHit != null ? `, direction hit ${(pred.directionHit * 100).toFixed(0)}%` : ""}).`
    : `${(weight * 100).toFixed(0)}% — model projects ${pred.pctReturn >= 0 ? "+" : ""}${pred.pctReturn.toFixed(1)}% at ${horizon}.`;
  parts.push(returnPart);

  // Cite the top-two factor contributions from the breakdown so the
  // "why" is grounded in the actual math (no LLM narration). Weighted
  // contribution = factor × horizon_weight.
  if (breakdown) {
    const w = HORIZON_WEIGHTS[horizon];
    const contributions: Array<{ label: string; value: number }> = [
      { label: "model return",       value: breakdown.returnFactor   * w.return },
      { label: `${horizon} momentum`, value: breakdown.momentumFactor * w.momentum },
      { label: "trend (MACD/ADX)",   value: breakdown.trendFactor    * w.trend },
      { label: "fundamental quality", value: breakdown.qualityFactor  * w.quality },
      { label: "value vs sector P/E", value: breakdown.valueFactor    * w.value },
      { label: "dividend yield",     value: breakdown.yieldFactor    * w.yield },
    ]
    .filter(c => Math.abs(c.value) > 0.05)
    .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
    if (contributions.length > 0) {
      const top = contributions.slice(0, 2).map(c =>
        `${c.label} ${c.value >= 0 ? "+" : ""}${c.value.toFixed(2)}`
      ).join(", ");
      parts.push(`Top factors: ${top}.`);
    }
  }

  if (t.signal) parts.push(`AI signal: ${t.signal}.`);
  if (t.volatility30d != null) {
    const isCalm = t.volatility30d < 1.5;
    parts.push(`Daily volatility ${t.volatility30d.toFixed(1)}% — ${isCalm ? `low for the ${risk} bucket` : "sized accordingly"}.`);
  }
  if (t.peRatio != null && SECTOR_MEDIAN_PE[t.sector] != null) {
    const rel = t.peRatio / SECTOR_MEDIAN_PE[t.sector];
    if (rel < 0.85) parts.push(`P/E ${t.peRatio.toFixed(1)}× is ${((1 - rel) * 100).toFixed(0)}% below sector median — value tilt.`);
    else if (rel > 1.15) parts.push(`P/E ${t.peRatio.toFixed(1)}× is ${((rel - 1) * 100).toFixed(0)}% above sector median — priced for growth.`);
  }
  if (t.dividendYield != null && t.dividendYield > 3) parts.push(`Trailing dividend yield ${t.dividendYield.toFixed(1)}% adds income.`);
  if (liquidityLoad > LIQUIDITY_IMPACT_CAP) {
    parts.push(`Position is ${(liquidityLoad * 100).toFixed(1)}% of one day's traded value — execution may move price.`);
  }
  parts.push(`Adds ${t.sector} exposure. Fitness ${fitness.toFixed(2)}.`);
  return parts;
}

function emptyMetrics(amountKes: number): PortfolioMetrics {
  return {
    expectedReturnPct: 0,
    expectedValueKes: amountKes,
    conservativeValueKes: amountKes,
    optimisticValueKes: amountKes,
    portfolioSigmaPct: 0,
    weightedMapePP: 0,
    sharpeRatio: null,
    riskBand: "Low",
    diversification: { hhi: 0, sectorCount: 0, avgPairwiseCorr: null, score: "Poor" },
    riskDrivers: ["No eligible tickers matched the filter — try relaxing risk or extending the horizon."],
  };
}
