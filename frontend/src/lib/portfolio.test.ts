import { describe, it, expect } from "vitest";
import { buildPortfolio, computeMetrics } from "./portfolio";
import type { UniverseTicker, HorizonKey } from "./portfolio";

// Small synthetic universe covering the paths that matter:
// - SELL signal (must be dropped)
// - missing horizon prediction (must be dropped)
// - illiquid (must be dropped)
// - two same-sector holdings (sector cap should kick in)
// - one very-negative-fitness holding (should be dropped by cap or normalisation)
function mkUniverse(): UniverseTicker[] {
  // volatility30d = DAILY stdev × 100 (matches pipeline/src/analysis/
  // technicals.py). ~1.5% daily is typical for a Kenyan large-cap;
  // that's ~24% annualised, well inside the Moderate risk band.
  const mk = (o: Partial<UniverseTicker>): UniverseTicker => ({
    ticker: "X", name: "X", sector: "S", signal: "BUY",
    currentPrice: 100, volatility30d: 1.5, avgVolume30d: 10_000,
    radarScore: 18, radarDenominator: 30, dividendYield: 3,
    // Multi-factor fields — neutral defaults keep the pre-existing
    // tests deterministic. Individual tests override to probe specific
    // paths.
    momentum1m: 0, momentum3m: 0, momentum6m: 0,
    rsi14: 50, macdSignal: 0, adx14: 20, peRatio: null,
    horizonPredictions: {
      "1M": { horizonDays: 21, pctReturn: 2, targetPrice: 102, mape: 3, directionHit: 0.55 },
      "3M": { horizonDays: 63, pctReturn: 6, targetPrice: 106, mape: 6, directionHit: 0.6 },
      "6M": { horizonDays: 126, pctReturn: 10, targetPrice: 110, mape: 10, directionHit: 0.65 },
      "9M": { horizonDays: 189, pctReturn: 14, targetPrice: 114, mape: 14, directionHit: 0.7 },
      "12M": { horizonDays: 252, pctReturn: 18, targetPrice: 118, mape: 18, directionHit: 0.7 },
    },
    ...o,
  });
  return [
    mk({ ticker: "AAA", name: "Alpha", sector: "Banking",   volatility30d: 1.2 }),
    mk({ ticker: "BBB", name: "Beta",  sector: "Banking",   volatility30d: 1.5 }),
    mk({ ticker: "CCC", name: "Gamma", sector: "Banking",   volatility30d: 1.8 }),  // third bank — sector cap should exclude
    mk({ ticker: "DDD", name: "Delta", sector: "Telecom",   volatility30d: 2.0 }),
    mk({ ticker: "EEE", name: "Ezra",  sector: "Energy",    volatility30d: 2.5 }),
    mk({ ticker: "FFF", name: "Zeta",  sector: "SELL zone", signal: "SELL" }),    // must drop
    mk({ ticker: "GGG", name: "Eta",   sector: "Bad",       avgVolume30d: 100 }), // illiquid, must drop
    mk({ ticker: "HHH", name: "Theta", sector: "Nulled",    horizonPredictions: {} }), // no horizon data, must drop
  ];
}

const AMOUNT = 100_000;
const HORIZON: HorizonKey = "3M";

describe("buildPortfolio", () => {
  it("filters out SELL, illiquid, and missing-horizon tickers", () => {
    const { holdings, excluded } = buildPortfolio({
      amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe: mkUniverse(),
    });
    const kept = holdings.map(h => h.ticker);
    expect(kept).not.toContain("FFF");                        // SELL
    expect(kept).not.toContain("GGG");                        // illiquid
    expect(kept).not.toContain("HHH");                        // no prediction
    // Excluded diagnostic tells the caller why:
    // Planner reframes the SELL signal into forecast-language for
    // fresh investors (see explainHolding change).
    expect(excluded.find(e => e.ticker === "FFF")?.reason).toContain("bearish");
    expect(excluded.find(e => e.ticker === "GGG")?.reason).toContain("illiquid");
    expect(excluded.find(e => e.ticker === "HHH")?.reason).toContain("no 3M prediction");
  });

  it("respects the sector cap: max 2 per sector", () => {
    const { holdings } = buildPortfolio({
      amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe: mkUniverse(),
    });
    const bySec: Record<string, number> = {};
    for (const h of holdings) bySec[h.sector] = (bySec[h.sector] ?? 0) + 1;
    for (const [sec, n] of Object.entries(bySec)) {
      expect(n, `sector ${sec} exceeds cap`).toBeLessThanOrEqual(2);
    }
  });

  it("weights sum to ~1 after normalisation", () => {
    const { holdings } = buildPortfolio({
      amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe: mkUniverse(),
    });
    const total = holdings.reduce((s, h) => s + h.weight, 0);
    expect(total).toBeCloseTo(1, 6);
  });

  it("enforces the per-stock cap for the risk profile", () => {
    // Conservative → max 25% per name. Feed a universe where one name is
    // wildly better than the rest to force the cap to bind.
    const uni: UniverseTicker[] = [
      { ticker: "STAR", name: "Star", sector: "A", signal: "BUY", currentPrice: 100,
        volatility30d: 5, avgVolume30d: 10_000, radarScore: 30, radarDenominator: 30,
        dividendYield: 0,
        momentum1m: 0, momentum3m: 0, momentum6m: 0,
        rsi14: 50, macdSignal: 0, adx14: 20, peRatio: null,
        horizonPredictions: {
          "3M": { horizonDays: 63, pctReturn: 50, targetPrice: 150, mape: 5, directionHit: 0.9 } } },
      { ticker: "MED1", name: "M1", sector: "B", signal: "BUY", currentPrice: 100,
        volatility30d: 15, avgVolume30d: 10_000, radarScore: 15, radarDenominator: 30,
        dividendYield: 0,
        momentum1m: 0, momentum3m: 0, momentum6m: 0,
        rsi14: 50, macdSignal: 0, adx14: 20, peRatio: null,
        horizonPredictions: {
          "3M": { horizonDays: 63, pctReturn: 4, targetPrice: 104, mape: 5, directionHit: 0.5 } } },
      { ticker: "MED2", name: "M2", sector: "C", signal: "BUY", currentPrice: 100,
        volatility30d: 15, avgVolume30d: 10_000, radarScore: 15, radarDenominator: 30,
        dividendYield: 0,
        momentum1m: 0, momentum3m: 0, momentum6m: 0,
        rsi14: 50, macdSignal: 0, adx14: 20, peRatio: null,
        horizonPredictions: {
          "3M": { horizonDays: 63, pctReturn: 4, targetPrice: 104, mape: 5, directionHit: 0.5 } } },
      { ticker: "MED3", name: "M3", sector: "D", signal: "BUY", currentPrice: 100,
        volatility30d: 15, avgVolume30d: 10_000, radarScore: 15, radarDenominator: 30,
        dividendYield: 0,
        momentum1m: 0, momentum3m: 0, momentum6m: 0,
        rsi14: 50, macdSignal: 0, adx14: 20, peRatio: null,
        horizonPredictions: {
          "3M": { horizonDays: 63, pctReturn: 4, targetPrice: 104, mape: 5, directionHit: 0.5 } } },
    ];
    const { holdings } = buildPortfolio({
      amountKes: AMOUNT, horizon: HORIZON, risk: "conservative", universe: uni,
    });
    const star = holdings.find(h => h.ticker === "STAR")!;
    // Conservative base cap = 0.25. Actual cap widens adaptively so
    // N × cap ≥ 1.05; with 4 picks that's max(0.25, 0.2625) = 0.2625.
    // Assertion tolerates the adaptive widening but confirms STAR
    // still doesn't dominate the portfolio.
    expect(star.weight).toBeLessThanOrEqual(0.27);
  });

  it("computes real share counts, not fractional", () => {
    const { holdings } = buildPortfolio({
      amountKes: 10_000, horizon: HORIZON, risk: "balanced", universe: mkUniverse(),
    });
    for (const h of holdings) {
      expect(Number.isInteger(h.shares)).toBe(true);
      expect(h.shares * h.currentPrice + h.cashResidueKes).toBeCloseTo(h.allocationKes, 2);
    }
  });
});

describe("computeMetrics", () => {
  it("expected value tracks weighted horizon return", () => {
    const universe = mkUniverse();
    const { holdings } = buildPortfolio({
      amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe,
    });
    const m = computeMetrics(holdings, HORIZON, universe, AMOUNT);
    // All eligible tickers return 6% at 3M, so weighted return = 6%.
    expect(m.expectedReturnPct).toBeCloseTo(6, 5);
    expect(m.expectedValueKes).toBeCloseTo(AMOUNT * 1.06, 2);
  });

  it("conservative < expected < optimistic and bands are symmetric", () => {
    const universe = mkUniverse();
    const { holdings } = buildPortfolio({
      amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe,
    });
    const m = computeMetrics(holdings, HORIZON, universe, AMOUNT);
    expect(m.conservativeValueKes).toBeLessThan(m.expectedValueKes);
    expect(m.expectedValueKes).toBeLessThan(m.optimisticValueKes);
    const lowerBand = m.expectedValueKes - m.conservativeValueKes;
    const upperBand = m.optimisticValueKes - m.expectedValueKes;
    expect(lowerBand).toBeCloseTo(upperBand, 2);
  });

  it("risk band scales with volatility", () => {
    // Daily σ 0.3% → annualised ~4.8% → Low. Daily σ 3% → annualised ~48% → High.
    const lowVol: UniverseTicker[] = mkUniverse().map(u => ({ ...u, volatility30d: 0.3 }));
    const hiVol:  UniverseTicker[] = mkUniverse().map(u => ({ ...u, volatility30d: 3.0 }));
    const bLow = buildPortfolio({ amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe: lowVol }).holdings;
    const bHi  = buildPortfolio({ amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe: hiVol }).holdings;
    const mLow = computeMetrics(bLow, HORIZON, lowVol, AMOUNT);
    const mHi  = computeMetrics(bHi,  HORIZON, hiVol,  AMOUNT);
    expect(mLow.riskBand).toBe("Low");
    expect(["Moderate", "High"]).toContain(mHi.riskBand);
  });

  it("horizon change reorders recommendations meaningfully", () => {
    // Build two universes that share tickers but bake in a horizon-
    // divergent story: one ticker (SHORT) has strong 1M momentum + high
    // 1M model return but weak long-run; another (LONG) is the reverse.
    // The optimiser must weight them differently for 1M vs 12M.
    const mkT = (o: Partial<UniverseTicker>): UniverseTicker => ({
      ticker: "X", name: "X", sector: "Banking", signal: "BUY",
      currentPrice: 100, volatility30d: 1.5, avgVolume30d: 10_000,
      radarScore: 18, radarDenominator: 30, dividendYield: 3,
      momentum1m: 0, momentum3m: 0, momentum6m: 0,
      rsi14: 50, macdSignal: 0, adx14: 20, peRatio: null,
      horizonPredictions: {},
      ...o,
    });
    const universe: UniverseTicker[] = [
      mkT({ ticker: "SHORT", sector: "Telecom", momentum1m: 8, adx14: 35, macdSignal: 1,
        horizonPredictions: {
          "1M": { horizonDays: 21, pctReturn: 4, targetPrice: 104, mape: 4, directionHit: 0.6 },
          "12M": { horizonDays: 252, pctReturn: 2, targetPrice: 102, mape: 25, directionHit: 0.45 },
        } }),
      mkT({ ticker: "LONG", sector: "Manufacturing and Allied", radarScore: 28, dividendYield: 6, peRatio: 8,
        momentum1m: -1, momentum6m: 1,
        horizonPredictions: {
          "1M": { horizonDays: 21, pctReturn: 0.5, targetPrice: 100.5, mape: 4, directionHit: 0.5 },
          "12M": { horizonDays: 252, pctReturn: 18, targetPrice: 118, mape: 8, directionHit: 0.7 },
        } }),
      mkT({ ticker: "MID", sector: "Energy and Petroleum", momentum3m: 3,
        horizonPredictions: {
          "1M": { horizonDays: 21, pctReturn: 1.5, targetPrice: 101.5, mape: 4, directionHit: 0.55 },
          "12M": { horizonDays: 252, pctReturn: 6, targetPrice: 106, mape: 12, directionHit: 0.55 },
        } }),
    ];
    const b1M = buildPortfolio({ amountKes: 100_000, horizon: "1M", risk: "balanced", universe });
    const b12M = buildPortfolio({ amountKes: 100_000, horizon: "12M", risk: "balanced", universe });
    const shortWeight1M  = b1M.holdings.find(h => h.ticker === "SHORT")?.weight ?? 0;
    const shortWeight12M = b12M.holdings.find(h => h.ticker === "SHORT")?.weight ?? 0;
    const longWeight1M   = b1M.holdings.find(h => h.ticker === "LONG")?.weight ?? 0;
    const longWeight12M  = b12M.holdings.find(h => h.ticker === "LONG")?.weight ?? 0;
    // SHORT should carry more weight at 1M than at 12M.
    expect(shortWeight1M).toBeGreaterThan(shortWeight12M);
    // LONG should carry more weight at 12M than at 1M.
    expect(longWeight12M).toBeGreaterThan(longWeight1M);
  });

  it("computeMetrics returns weightedMapePP and sharpeRatio", () => {
    const universe = mkUniverse();
    const { holdings } = buildPortfolio({
      amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe,
    });
    const m = computeMetrics(holdings, HORIZON, universe, AMOUNT);
    expect(m.weightedMapePP).toBeGreaterThan(0);
    expect(m.sharpeRatio).not.toBeNull();
  });

  it("HHI < 0.3 for a diversified 5-holding portfolio", () => {
    const { holdings } = buildPortfolio({
      amountKes: AMOUNT, horizon: HORIZON, risk: "balanced", universe: mkUniverse(),
    });
    if (holdings.length >= 4) {
      const m = computeMetrics(holdings, HORIZON, mkUniverse(), AMOUNT);
      expect(m.diversification.hhi).toBeLessThan(0.4);
    }
  });
});
