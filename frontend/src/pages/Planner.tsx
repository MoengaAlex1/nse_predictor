import { useMemo, useState } from "react";
import type { FC } from "react";
import { Link } from "react-router-dom";
import { usePortfolioUniverse } from "../hooks/usePortfolioUniverse";
import { buildPortfolio, computeMetrics } from "../lib/portfolio";
import type { HorizonKey, RiskProfile, Holding, PortfolioMetrics } from "../lib/portfolio";
import { fmtKes, fmtCompactKes, fmtPct } from "../lib/format";
import { Card } from "../components/ui/Card";

// Investment Planner / Portfolio Builder.
// User enters amount + horizon + risk profile; the page reads the
// full 62-ticker universe from Firestore (via usePortfolioUniverse),
// runs the deterministic score-ranked optimiser (lib/portfolio.ts),
// and lays out the recommendation with projection bands and per-stock
// rationale. Read-only in this first cut — customisation + save land
// in Phase 3/4.

const HORIZONS: { key: HorizonKey; label: string }[] = [
  { key: "1M", label: "1 Month" },
  { key: "3M", label: "3 Months" },
  { key: "6M", label: "6 Months" },
  { key: "9M", label: "9 Months" },
  { key: "12M", label: "1 Year" },
];

const RISK_OPTIONS: { key: RiskProfile; label: string; sub: string }[] = [
  { key: "conservative", label: "Conservative", sub: "Lower risk, lower volatility, income-friendly" },
  { key: "balanced",     label: "Balanced",     sub: "Middle ground — mix of growth and stability" },
  { key: "growth",       label: "Growth",       sub: "Higher risk for higher upside" },
];

const AMOUNT_PRESETS = [10_000, 50_000, 100_000, 500_000, 1_000_000];

export const Planner: FC = () => {
  const [amount, setAmount] = useState<number>(100_000);
  const [horizon, setHorizon] = useState<HorizonKey>("3M");
  const [risk, setRisk] = useState<RiskProfile>("balanced");
  const [submitted, setSubmitted] = useState(false);

  const { isLoading, universe, correlation, correlationUpdatedAt } = usePortfolioUniverse();

  const build = useMemo(() => {
    if (!submitted || !universe.length) return null;
    return buildPortfolio({ amountKes: amount, horizon, risk, universe, correlation });
  }, [submitted, universe, correlation, amount, horizon, risk]);

  const metrics = useMemo<PortfolioMetrics | null>(() => {
    if (!build || build.holdings.length === 0) return null;
    return computeMetrics(build.holdings, horizon, universe, amount, correlation);
  }, [build, horizon, universe, amount, correlation]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-bold text-ink">Investment Planner</h1>
        <p className="mt-1 text-sub">
          Enter your amount, horizon and risk profile. The system builds a portfolio
          from the NSE stocks the platform is already tracking.
        </p>
      </header>

      <InputsCard
        amount={amount} setAmount={setAmount}
        horizon={horizon} setHorizon={setHorizon}
        risk={risk} setRisk={setRisk}
        onSubmit={() => setSubmitted(true)}
        universeReady={universe.length > 0}
      />

      {submitted && isLoading && (
        <Card className="border-rim bg-surface">
          <p className="text-sm text-sub">Loading universe from Firestore… ~62 tickers, one-shot batched read.</p>
        </Card>
      )}

      {submitted && !isLoading && build && build.holdings.length === 0 && (
        <Card className="border-amber-400 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40">
          <p className="text-sm text-amber-900 dark:text-amber-300">
            No eligible tickers matched the filter for your inputs.
            Try relaxing the risk profile, choosing a longer horizon,
            or lowering the liquidity floor.
          </p>
          {build.excluded.slice(0, 6).map(e => (
            <p key={e.ticker} className="mt-1 text-[11px] text-amber-800 dark:text-amber-400">
              {e.ticker}: {e.reason}
            </p>
          ))}
        </Card>
      )}

      {submitted && !isLoading && build && build.holdings.length > 0 && metrics && (
        <>
          <RecommendationCard holdings={build.holdings} amount={amount} horizon={horizon} risk={risk} />
          <ProjectionCard metrics={metrics} amount={amount} horizon={horizon} />
          <RiskCard metrics={metrics} correlationUpdatedAt={correlationUpdatedAt} correlationAvailable={!!correlation} />
          <WhyCard holdings={build.holdings} excluded={build.excluded} />
        </>
      )}

      {submitted && !isLoading && (
        <Card className="border-rim bg-surface">
          <p className="text-[11px] leading-relaxed text-hint">
            <strong>Not investment advice.</strong> Projections are derived from the platform's model
            outputs (LightGBM multi-horizon target × walk-forward direction hit) and ±1.5σ bands built
            from 30-day realised volatility scaled to the horizon. Actual returns will differ.
            The model's own backtest error (MAPE) is shown next to each stock. Historical performance
            is not a guarantee of future results.
          </p>
        </Card>
      )}
    </div>
  );
};

// ─── Inputs ─────────────────────────────────────────────────────────────────

const InputsCard: FC<{
  amount: number; setAmount: (v: number) => void;
  horizon: HorizonKey; setHorizon: (v: HorizonKey) => void;
  risk: RiskProfile; setRisk: (v: RiskProfile) => void;
  onSubmit: () => void;
  universeReady: boolean;
}> = ({ amount, setAmount, horizon, setHorizon, risk, setRisk, onSubmit, universeReady }) => (
  <Card className="border-rim bg-surface">
    <div className="grid gap-4 md:grid-cols-[1fr_1fr_1fr_auto]">
      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-hint">
          Investment amount (KES)
        </label>
        <input
          type="number"
          value={amount}
          min={1000}
          step={1000}
          onChange={(e) => setAmount(Math.max(1000, Number(e.target.value) || 0))}
          className="w-full rounded-md border border-seam bg-canvas px-3 py-2 font-mono text-sm tabular-nums text-ink outline-none focus:border-accent"
        />
        <div className="mt-1.5 flex flex-wrap gap-1">
          {AMOUNT_PRESETS.map(v => (
            <button
              key={v}
              type="button"
              onClick={() => setAmount(v)}
              className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold transition-colors ${
                amount === v
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-seam bg-raised/40 text-hint hover:text-ink"
              }`}
            >
              {v >= 1_000_000 ? `${v / 1_000_000}M` : `${v / 1_000}K`}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-hint">
          Investment period
        </label>
        <div className="flex flex-wrap gap-1">
          {HORIZONS.map(h => (
            <button
              key={h.key}
              type="button"
              onClick={() => setHorizon(h.key)}
              className={`rounded-md border px-2 py-1.5 text-xs font-semibold transition-colors ${
                horizon === h.key
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-seam bg-raised/40 text-sub hover:text-ink"
              }`}
            >
              {h.label}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-hint">
          Risk profile
        </label>
        <div className="flex flex-col gap-1">
          {RISK_OPTIONS.map(r => (
            <button
              key={r.key}
              type="button"
              onClick={() => setRisk(r.key)}
              className={`rounded-md border px-2 py-1.5 text-left text-xs transition-colors ${
                risk === r.key
                  ? "border-accent bg-accent/10 text-accent"
                  : "border-seam bg-raised/40 text-sub hover:text-ink"
              }`}
            >
              <div className="font-semibold">{r.label}</div>
              <div className="text-[10px] text-hint">{r.sub}</div>
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-end">
        <button
          type="button"
          onClick={onSubmit}
          disabled={!universeReady}
          className="rounded-md bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Build my portfolio
        </button>
      </div>
    </div>
  </Card>
);

// ─── Recommendation ─────────────────────────────────────────────────────────

const RecommendationCard: FC<{
  holdings: Holding[]; amount: number; horizon: HorizonKey; risk: RiskProfile;
}> = ({ holdings, amount, horizon, risk }) => (
  <Card className="border-rim bg-surface">
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-sm font-semibold text-ink">Recommended portfolio</h2>
      <p className="text-[11px] text-hint">
        {fmtKes(amount)} · {HORIZONS.find(h => h.key === horizon)?.label} · {risk.charAt(0).toUpperCase() + risk.slice(1)}
      </p>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-seam text-[10px] uppercase tracking-wider text-muted">
            <th className="py-2 pr-3 text-left">Stock</th>
            <th className="py-2 pr-3 text-right">Sector</th>
            <th className="py-2 pr-3 text-right">Weight</th>
            <th className="py-2 pr-3 text-right">Allocation</th>
            <th className="py-2 pr-3 text-right">Price</th>
            <th className="py-2 pr-3 text-right">Shares</th>
            <th className="py-2 pl-3 text-right">Cash residue</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-seam/50">
          {holdings.map(h => (
            <tr key={h.ticker} className="hover:bg-raised/40">
              <td className="py-2.5 pr-3">
                <Link
                  to={`/chart/${h.ticker}`}
                  className="font-semibold text-ink hover:text-accent"
                >
                  {h.ticker}
                </Link>
                <div className="text-[11px] text-hint">{h.name}</div>
              </td>
              <td className="py-2.5 pr-3 text-right text-[11px] text-sub">{h.sector}</td>
              <td className="py-2.5 pr-3 text-right font-mono font-semibold tabular-nums text-ink">
                {(h.weight * 100).toFixed(1)}%
              </td>
              <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-ink">
                {fmtKes(h.allocationKes)}
              </td>
              <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-sub">
                {fmtKes(h.currentPrice)}
              </td>
              <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-sub">
                {h.shares.toLocaleString("en-KE")}
              </td>
              <td className="py-2.5 pl-3 text-right font-mono tabular-nums text-hint">
                {fmtKes(h.cashResidueKes)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </Card>
);

// ─── Projection ─────────────────────────────────────────────────────────────

const ProjectionCard: FC<{
  metrics: PortfolioMetrics; amount: number; horizon: HorizonKey;
}> = ({ metrics, amount, horizon }) => {
  const label = HORIZONS.find(h => h.key === horizon)?.label ?? horizon;
  const gain = metrics.expectedValueKes - amount;
  const gainPct = metrics.expectedReturnPct;
  return (
    <Card className="border-rim bg-surface">
      <h2 className="mb-1 text-sm font-semibold text-ink">Projection · {label}</h2>
      <p className="mb-4 text-[11px] text-hint">
        Bands are ±1.5σ around the expected value. σ = weighted portfolio volatility scaled to the horizon.
        Not a guarantee.
      </p>
      <div className="grid gap-3 md:grid-cols-3">
        <ScenarioTile
          label="Conservative"
          value={metrics.conservativeValueKes}
          amount={amount}
          tone="down"
          note="Lower band — ~7th percentile"
        />
        <ScenarioTile
          label="Expected"
          value={metrics.expectedValueKes}
          amount={amount}
          tone={gain >= 0 ? "up" : "down"}
          note={`${gain >= 0 ? "+" : ""}${fmtPct(gainPct)} weighted horizon return`}
        />
        <ScenarioTile
          label="Optimistic"
          value={metrics.optimisticValueKes}
          amount={amount}
          tone="up"
          note="Upper band — ~93rd percentile"
        />
      </div>
    </Card>
  );
};

const ScenarioTile: FC<{
  label: string; value: number; amount: number;
  tone: "up" | "down"; note: string;
}> = ({ label, value, amount, tone, note }) => {
  const gain = value - amount;
  const tint = tone === "up"
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400";
  return (
    <div className="rounded-lg border border-seam bg-raised/40 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</p>
      <p className={`mt-1 font-mono text-xl font-bold tabular-nums ${tint}`}>{fmtKes(value)}</p>
      <p className={`mt-0.5 font-mono text-xs tabular-nums ${tint}`}>
        {gain >= 0 ? "+" : "−"}{fmtKes(Math.abs(gain), { prefix: false })}
      </p>
      <p className="mt-1 text-[10px] text-hint">{note}</p>
    </div>
  );
};

// ─── Risk ───────────────────────────────────────────────────────────────────

const RiskCard: FC<{
  metrics: PortfolioMetrics;
  correlationUpdatedAt: string | null;
  correlationAvailable: boolean;
}> = ({ metrics, correlationUpdatedAt, correlationAvailable }) => {
  const tone =
    metrics.riskBand === "Low"      ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800" :
    metrics.riskBand === "Moderate" ? "bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-800" :
                                       "bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-400 border-red-300 dark:border-red-800";
  return (
    <Card className={`border ${tone}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Portfolio risk · {metrics.riskBand}</h2>
        <p className="text-[11px] opacity-80">
          Annualised σ ≈ {(metrics.portfolioSigmaPct * Math.sqrt(252 / 63)).toFixed(1)}% ·
          HHI {metrics.diversification.hhi.toFixed(2)} ·
          {metrics.diversification.sectorCount} sectors · Diversification: {metrics.diversification.score}
        </p>
      </div>
      {metrics.riskDrivers.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {metrics.riskDrivers.map((d, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <span className="mt-0.5 shrink-0 font-bold">›</span>
              <span>{d}</span>
            </li>
          ))}
        </ul>
      )}
      {!correlationAvailable && (
        <p className="mt-3 text-[11px] italic opacity-80">
          Correlation matrix not yet populated (weekly job hasn't run). Using 0.3 avg-pair prior.
        </p>
      )}
      {correlationAvailable && correlationUpdatedAt && (
        <p className="mt-3 text-[11px] opacity-70">
          Correlation matrix updated {new Date(correlationUpdatedAt).toLocaleDateString("en-GB")}.
        </p>
      )}
    </Card>
  );
};

// ─── Why this portfolio? ────────────────────────────────────────────────────

const WhyCard: FC<{
  holdings: Holding[];
  excluded: Array<{ ticker: string; reason: string }>;
}> = ({ holdings, excluded }) => (
  <Card className="border-rim bg-surface">
    <h2 className="mb-3 text-sm font-semibold text-ink">Why these stocks?</h2>
    <div className="space-y-3">
      {holdings.map(h => (
        <div key={h.ticker} className="rounded-md border border-seam bg-raised/30 p-3">
          <div className="mb-1.5 flex items-baseline justify-between">
            <Link
              to={`/chart/${h.ticker}`}
              className="text-sm font-semibold text-ink hover:text-accent"
            >
              {h.ticker} · {h.name}
            </Link>
            <span className="font-mono text-xs text-hint">
              {(h.weight * 100).toFixed(1)}% · {fmtCompactKes(h.allocationKes)}
            </span>
          </div>
          <ul className="space-y-0.5 text-[11px] leading-relaxed text-sub">
            {h.reasons.map((r, i) => <li key={i}>· {r}</li>)}
          </ul>
        </div>
      ))}
    </div>
    {excluded.length > 0 && (
      <details className="mt-4 rounded border border-seam/60 bg-raised/20 p-2">
        <summary className="cursor-pointer text-[11px] font-semibold text-hint">
          Why some tickers were excluded ({excluded.length})
        </summary>
        <ul className="mt-2 space-y-0.5 text-[11px] text-hint">
          {excluded.slice(0, 20).map(e => (
            <li key={e.ticker}>{e.ticker}: {e.reason}</li>
          ))}
        </ul>
      </details>
    )}
  </Card>
);
