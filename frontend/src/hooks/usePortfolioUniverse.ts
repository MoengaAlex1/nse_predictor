import { useQuery, useQueries } from "@tanstack/react-query";
import { doc, getDoc } from "firebase/firestore";
import { db } from "../lib/firebase";
import { useCompanies } from "./useCompanies";
import {
  fetchLatestSnapshot,
  fetchLatestTechnicals,
  fetchFinancials,
} from "../lib/firestore";
import type { UniverseTicker, HorizonKey } from "../lib/portfolio";
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, FinancialsDoc } from "../types";

// Portfolio Builder universe reader. One-shot batched view:
//   companies feed (already cached by useCompanies)
//   + per-ticker snapshot (for horizon_predictions + signal)
//   + per-ticker technicals (for volatility_30d + avg_volume_30d)
//   + per-ticker financials (for trailing-12M dividend yield only)
//   + market_overview/correlation_60d (single doc, single read)
//
// Uses useQueries so all per-ticker reads run in parallel with the same
// react-query staleness contract other pages get. Returns a normalised
// UniverseTicker[] the portfolio math library can consume directly.

const HORIZONS: HorizonKey[] = ["1M", "3M", "6M", "9M", "12M"];

// Trailing return % from a price_history array. Windows are in trading
// days (~21/63/126). Falls back to null when the history is too short
// or the anchor price is missing/zero.
function trailingReturn(history: { date: string; price: number }[] | undefined | null, tradingDays: number): number | null {
  if (!history || history.length < tradingDays + 1) return null;
  const now = history[history.length - 1]?.price;
  const then = history[history.length - 1 - tradingDays]?.price;
  if (!now || !then || then <= 0) return null;
  return ((now / then) - 1) * 100;
}

function macdSignSafe(macdHist: number | null | undefined): -1 | 0 | 1 | null {
  if (macdHist == null || !Number.isFinite(macdHist)) return null;
  if (macdHist > 0.01) return 1;
  if (macdHist < -0.01) return -1;
  return 0;
}

function latestPositiveEps(fin: FinancialsDoc | null | undefined): number | null {
  if (!fin?.annual?.length) return null;
  for (const r of fin.annual) {
    if (r.eps != null && r.eps > 0) return r.eps;
  }
  return null;
}

interface CorrelationDoc {
  updated_at: string;
  window_days: number;
  tickers: string[];
  matrix: Record<string, Record<string, number>>;
}

function trailingDividendYield(fin: FinancialsDoc | null, price: number | null): number | null {
  if (!fin || !price || price <= 0) return null;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 365);
  const cutoffIso = cutoff.toISOString().slice(0, 10);
  let ttm = 0;
  for (const d of fin.dividends ?? []) {
    const dd = d.announcement_date ?? d.ex_date ?? null;
    if (!dd) continue;
    if (dd < cutoffIso) continue;
    if (d.amount_kes != null && d.amount_kes > 0) ttm += d.amount_kes;
  }
  return ttm > 0 ? (ttm / price) * 100 : null;
}

function radarScoreCoarse(_fin: FinancialsDoc | null): { score: number | null; denom: number } {
  // Cheap proxy — the full RadarScoreCard already extracts the 5-axis
  // vector; a portfolio-time read doesn't need the SVG, just the total.
  // Kept null-first so a ticker with no financials doesn't bias the
  // fitness function.
  if (!_fin?.annual?.length) return { score: null, denom: 30 };
  const recent = _fin.annual.slice(0, 5);
  const positiveEpsYears = recent.filter(a => (a.eps ?? 0) > 0).length;
  const positiveBvps = recent.some(a => (a.bvps ?? 0) > 0);
  const paysDividend = (_fin.dividends ?? []).length > 0;
  const health = Math.round((positiveEpsYears / recent.length) * 4)
               + (positiveBvps ? 1 : 0)
               + (paysDividend ? 1 : 0);
  return { score: Math.min(30, health * 5), denom: 30 };
}

export interface PortfolioUniverseResult {
  isLoading: boolean;
  universe: UniverseTicker[];
  correlation: Record<string, Record<string, number>> | undefined;
  correlationUpdatedAt: string | null;
}

export function usePortfolioUniverse(): PortfolioUniverseResult {
  const { data: companies = [], isLoading: companiesLoading } = useCompanies();

  // Correlation matrix is one doc — fine to fetch with a plain useQuery.
  const corrQuery = useQuery<CorrelationDoc | null>({
    queryKey: ["portfolio", "correlation_60d"],
    queryFn: async () => {
      const snap = await getDoc(doc(db, "market_overview", "correlation_60d"));
      return snap.exists() ? (snap.data() as CorrelationDoc) : null;
    },
    staleTime: 1000 * 60 * 60 * 24,   // correlation moves slowly
  });

  const tickers = companies.map(c => c.short).filter(Boolean);

  // useQueries lets react-query parallelise, dedupe, and cache per key.
  // 62 tickers × 3 collections = ~186 reads on first paint, subsequent
  // navigations hit cache. Firestore free-tier daily quota is 50k, so
  // even 100 users/day of the Planner sits well inside budget.
  const snapshotQueries = useQueries({
    queries: tickers.map(t => ({
      queryKey: ["snapshot", t],
      queryFn: () => fetchLatestSnapshot(t),
      staleTime: 1000 * 60 * 15,
    })),
  });
  const technicalsQueries = useQueries({
    queries: tickers.map(t => ({
      queryKey: ["technicals", t],
      queryFn: () => fetchLatestTechnicals(t),
      staleTime: 1000 * 60 * 60,
    })),
  });
  const financialsQueries = useQueries({
    queries: tickers.map(t => ({
      queryKey: ["financials", t],
      queryFn: () => fetchFinancials(t),
      staleTime: 1000 * 60 * 60,
    })),
  });

  const anyLoading = companiesLoading
    || corrQuery.isLoading
    || snapshotQueries.some(q => q.isLoading)
    || technicalsQueries.some(q => q.isLoading)
    || financialsQueries.some(q => q.isLoading);

  const universe: UniverseTicker[] = companies.map((c: CompanyDoc, idx) => {
    const snap = snapshotQueries[idx]?.data as SnapshotDoc | null | undefined;
    const tech = technicalsQueries[idx]?.data as TechnicalsDoc | null | undefined;
    const fin  = financialsQueries[idx]?.data as FinancialsDoc | null | undefined;

    const price = c.current_price ?? c.last_known_price ?? null;

    // Snapshot's horizon_predictions map straight to our HorizonPrediction
    // shape — snake→camel only.
    const horizonPredictions: UniverseTicker["horizonPredictions"] = {};
    if (snap?.horizon_predictions) {
      for (const k of HORIZONS) {
        const hp = snap.horizon_predictions[k];
        if (!hp) continue;
        horizonPredictions[k] = {
          horizonDays:  hp.horizon_days,
          pctReturn:    hp.pct_return,
          targetPrice:  hp.target_price,
          mape:         hp.mape,
          directionHit: hp.direction_hit,
        };
      }
    }

    const radar = radarScoreCoarse(fin ?? null);

    // Multi-factor signals — sourced from data the platform already
    // computes. Every field is null-safe; the fitness function drops
    // missing factors from the weighted sum instead of penalising.
    const priceHistory = c.price_history ?? [];
    const eps = latestPositiveEps(fin);

    return {
      ticker:            c.short,
      name:              c.name ?? c.short,
      sector:            c.sector ?? "Uncategorised",
      signal:            (snap?.risk_adjusted_signal ?? snap?.signal ?? null) as UniverseTicker["signal"],
      currentPrice:      price,
      volatility30d:     tech?.volatility_30d ?? null,
      avgVolume30d:      tech?.avg_volume_30d ?? null,
      radarScore:        radar.score,
      radarDenominator:  radar.denom,
      dividendYield:     trailingDividendYield(fin ?? null, price),
      horizonPredictions,

      // Multi-factor fields
      momentum1m: trailingReturn(priceHistory, 21),
      momentum3m: trailingReturn(priceHistory, 63),
      momentum6m: trailingReturn(priceHistory, 126),
      rsi14:       tech?.rsi_14 ?? null,
      macdSignal:  macdSignSafe(tech?.macd_hist),
      adx14:       tech?.adx_14 ?? null,
      peRatio:     (price && eps && eps > 0) ? price / eps : null,
    };
  });

  return {
    isLoading: anyLoading,
    universe,
    correlation: corrQuery.data?.matrix,
    correlationUpdatedAt: corrQuery.data?.updated_at ?? null,
  };
}
