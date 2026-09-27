import { useEffect, useMemo, useState } from "react";
import type { FC } from "react";
import { Link } from "react-router-dom";
import { usePortfolioUniverse } from "../hooks/usePortfolioUniverse";
import { useUserPortfolios, type SavedPortfolio } from "../hooks/useUserPortfolios";
import { buildPortfolio, computeMetrics, mmfProjection } from "../lib/portfolio";
import type { HorizonKey, RiskProfile, Holding, PortfolioMetrics } from "../lib/portfolio";
import { fmtKes, fmtCompactKes, fmtPct } from "../lib/format";
import { Card } from "../components/ui/Card";
import { CustomizePanel } from "../components/planner/CustomizePanel";
import { RecommendedVsCustom } from "../components/planner/RecommendedVsCustom";
import { SavedPortfoliosDrawer } from "../components/planner/SavedPortfoliosDrawer";

// Investment Planner / Portfolio Builder — orchestrator.
// - Reads the universe + correlation matrix (usePortfolioUniverse)
// - Runs the deterministic optimiser (lib/portfolio.buildPortfolio)
// - Renders inputs → recommendation → projection → risk → why
// - Phase 3: Customize + live recalc + Recommended-vs-Custom compare
// - Phase 4: Save/Load user portfolios via users/{uid}/portfolios/{id}

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
  // ── Inputs ────────────────────────────────────────────────────────────
  const [amount, setAmount] = useState<number>(100_000);
  const [horizon, setHorizon] = useState<HorizonKey>("3M");
  const [risk, setRisk] = useState<RiskProfile>("balanced");
  const [submitted, setSubmitted] = useState(false);

  // ── Data ──────────────────────────────────────────────────────────────
  const { isLoading, universe, correlation, correlationUpdatedAt } = usePortfolioUniverse();
  const { isSignedIn, portfolios, isLoading: portfoliosLoading, save, remove, saving } = useUserPortfolios();

  // ── Recommendation (pure derivation) ──────────────────────────────────
  const build = useMemo(() => {
    if (!submitted || !universe.length) return null;
    return buildPortfolio({ amountKes: amount, horizon, risk, universe, correlation });
  }, [submitted, universe, correlation, amount, horizon, risk]);

  const recommendedMetrics = useMemo<PortfolioMetrics | null>(() => {
    if (!build || build.holdings.length === 0) return null;
    return computeMetrics(build.holdings, horizon, universe, amount, correlation);
  }, [build, horizon, universe, amount, correlation]);

  // ── Custom portfolio state (Phase 3) ──────────────────────────────────
  // Starts as null → "no edits yet". Once the user touches Customize, it
  // becomes a Holding[] and drives the Custom side of the compare table.
  // Reset button sets it back to null (which also collapses the compare).
  const [customHoldings, setCustomHoldings] = useState<Holding[] | null>(null);

  // Every time the recommendation changes (new inputs), reset custom edits
  // to avoid a stale comparison against a different recommendation.
  useEffect(() => {
    setCustomHoldings(null);
    setLastSaveId(null);
  }, [amount, horizon, risk, universe.length]);

  const customMetrics = useMemo<PortfolioMetrics | null>(() => {
    if (!customHoldings || customHoldings.length === 0) return null;
    return computeMetrics(customHoldings, horizon, universe, amount, correlation);
  }, [customHoldings, horizon, universe, amount, correlation]);

  // ── Save/Load (Phase 4) ───────────────────────────────────────────────
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [lastSaveId, setLastSaveId] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function handleSave(): Promise<void> {
    if (!build || !recommendedMetrics) return;
    setSaveError(null);
    try {
      const id = await save({
        id: lastSaveId ?? undefined,
        name: saveName.trim() || `${horizon} ${risk} · ${new Date().toLocaleDateString("en-GB")}`,
        inputs: { amountKes: amount, horizon, risk },
        recommended: { holdings: build.holdings, metrics: recommendedMetrics },
        custom: customHoldings && customMetrics
          ? { holdings: customHoldings, metrics: customMetrics }
          : null,
      });
      setLastSaveId(id);
      setSaveModalOpen(false);
      setSaveName("");
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Save failed.");
    }
  }

  function handleLoad(p: SavedPortfolio): void {
    setAmount(p.inputs.amountKes);
    setHorizon(p.inputs.horizon);
    setRisk(p.inputs.risk);
    setSubmitted(true);
    // Custom edits carry over if the saved portfolio has any.
    setCustomHoldings(p.custom?.holdings ?? null);
    setLastSaveId(p.id);
  }

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h1 className="text-3xl font-bold text-ink">Investment Planner</h1>
          <p className="mt-1 text-sub">
            Enter your amount, horizon and risk profile. The system builds a portfolio
            from the NSE stocks the platform is already tracking. Edit it in place, save
            it, and compare your version to the recommendation.
          </p>
        </div>
      </header>

      {/* Explainer for first-time users. The rest of the platform uses
          BUY/HOLD/SELL signals that are written for existing holders;
          in the Planner we translate everything to a forward-looking
          allocation view so a fresh investor isn't reading holder-
          management language when deciding where to put new money. */}
      <Card className="border-sky-300 dark:border-sky-800 bg-sky-50 dark:bg-sky-950/30">
        <p className="text-xs font-semibold text-sky-800 dark:text-sky-300">How this works</p>
        <p className="mt-1 text-[12px] leading-relaxed text-sky-900 dark:text-sky-200">
          This tool is for <strong>allocating new money</strong> — not for managing
          positions you already hold. It ranks NSE stocks by the model's per-horizon
          forecast (LightGBM target × walk-forward accuracy), current momentum and
          technicals, fundamental quality, sector-relative valuation, and dividend yield.
          The tickers you see are combinations the model expects to earn a positive
          return over your chosen period. If the model sees no attractive setups, the
          page will surface a money-market alternative instead of forcing a bad
          recommendation. The BUY/HOLD/SELL badges you'll see elsewhere on the platform
          are written for existing shareholders and aren't used here.
        </p>
      </Card>

      <InputsCard
        amount={amount} setAmount={setAmount}
        horizon={horizon} setHorizon={setHorizon}
        risk={risk} setRisk={setRisk}
        onSubmit={() => setSubmitted(true)}
        universeReady={universe.length > 0}
      />

      <SavedPortfoliosDrawer
        isSignedIn={isSignedIn}
        portfolios={portfolios}
        isLoading={portfoliosLoading}
        onLoad={handleLoad}
        onDelete={remove}
      />

      {submitted && isLoading && (
        <Card className="border-rim bg-surface">
          <p className="text-sm text-sub">Loading universe from Firestore…</p>
        </Card>
      )}

      {submitted && !isLoading && build && build.holdings.length === 0 && (
        <MmfFallbackCard
          amount={amount}
          horizon={horizon}
          excluded={build.excluded}
          reason="none-eligible"
        />
      )}

      {/* Model bearish: picks were made but the weighted expected return
          is still negative. Show the honest "consider cash" alternative
          alongside the equity recommendation so the user isn't pushed
          into a projected loss. */}
      {submitted && !isLoading && build && build.holdings.length > 0 && recommendedMetrics && recommendedMetrics.expectedReturnPct < 0 && (
        <MmfFallbackCard
          amount={amount}
          horizon={horizon}
          excluded={build.excluded}
          reason="negative-equity-view"
          equityReturnPct={recommendedMetrics.expectedReturnPct}
        />
      )}

      {submitted && !isLoading && build && build.holdings.length > 0 && recommendedMetrics && (
        <>
          <RecommendationCard
            holdings={build.holdings}
            amount={amount}
            horizon={horizon}
            risk={risk}
            onSave={() => { setSaveName(defaultSaveName(horizon, risk)); setSaveModalOpen(true); }}
            onCustomize={() => setCustomHoldings(build.holdings)}
            canSave={isSignedIn}
          />
          <ProjectionCard metrics={recommendedMetrics} amount={amount} horizon={horizon} />
          <RiskCard
            metrics={recommendedMetrics}
            correlationUpdatedAt={correlationUpdatedAt}
            correlationAvailable={!!correlation}
          />
          <WhyCard holdings={build.holdings} excluded={build.excluded} />

          {/* Phase 3 — customize & compare. Only mounts once the user
              clicks "Customize" on the recommendation card. */}
          {customHoldings !== null && (
            <>
              <CustomizePanel
                amountKes={amount}
                holdings={customHoldings}
                universe={universe}
                onChange={setCustomHoldings}
                onReset={() => setCustomHoldings(build.holdings)}
              />
              <RecommendedVsCustom
                amountKes={amount}
                recommended={recommendedMetrics}
                custom={customMetrics}
              />
            </>
          )}
        </>
      )}

      {saveModalOpen && (
        <SaveModal
          name={saveName}
          setName={setSaveName}
          onConfirm={handleSave}
          onCancel={() => { setSaveModalOpen(false); setSaveError(null); }}
          saving={saving}
          error={saveError}
        />
      )}

      {submitted && !isLoading && (
        <Card className="border-rim bg-surface">
          <p className="text-[11px] leading-relaxed text-hint">
            <strong>Not investment advice.</strong> Projections are derived from the
            platform's model outputs (LightGBM multi-horizon target × walk-forward
            direction hit) and ±1.5σ bands built from 30-day realised volatility
            scaled to the horizon. Actual returns will differ. Historical performance
            is not a guarantee of future results.
          </p>
        </Card>
      )}
    </div>
  );
};

function defaultSaveName(horizon: HorizonKey, risk: RiskProfile): string {
  return `${horizon} ${risk.charAt(0).toUpperCase() + risk.slice(1)} · ${new Date().toLocaleDateString("en-GB")}`;
}

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

// ─── Recommendation card ────────────────────────────────────────────────────

const RecommendationCard: FC<{
  holdings: Holding[];
  amount: number;
  horizon: HorizonKey;
  risk: RiskProfile;
  onSave: () => void;
  onCustomize: () => void;
  canSave: boolean;
}> = ({ holdings, amount, horizon, risk, onSave, onCustomize, canSave }) => (
  <Card className="border-rim bg-surface">
    <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
      <h2 className="text-sm font-semibold text-ink">Recommended portfolio</h2>
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-[11px] text-hint">
          {fmtKes(amount)} · {HORIZONS.find(h => h.key === horizon)?.label} · {risk.charAt(0).toUpperCase() + risk.slice(1)}
        </p>
        <button
          type="button"
          onClick={onCustomize}
          className="rounded border border-accent bg-accent/10 px-2 py-1 text-[11px] font-semibold text-accent hover:bg-accent/20"
        >
          Customize
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={!canSave}
          className="rounded border border-seam bg-raised/40 px-2 py-1 text-[11px] font-semibold text-sub hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          title={canSave ? "Save this plan to your account" : "Sign in to save portfolios"}
        >
          Save
        </button>
      </div>
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
                <Link to={`/chart/${h.ticker}`} className="font-semibold text-ink hover:text-accent">
                  {h.ticker}
                </Link>
                <div className="text-[11px] text-hint">{h.name}</div>
              </td>
              <td className="py-2.5 pr-3 text-right text-[11px] text-sub">{h.sector}</td>
              <td className="py-2.5 pr-3 text-right font-mono font-semibold tabular-nums text-ink">
                {(h.weight * 100).toFixed(1)}%
              </td>
              <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-ink">{fmtKes(h.allocationKes)}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-sub">{fmtKes(h.currentPrice)}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular-nums text-sub">{h.shares.toLocaleString("en-KE")}</td>
              <td className="py-2.5 pl-3 text-right font-mono tabular-nums text-hint">{fmtKes(h.cashResidueKes)}</td>
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
        Bands combine ±1.5σ price volatility (correlation-adjusted) and ±1.5 × the model's
        walk-forward MAPE. Not a guarantee.
      </p>
      <div className="grid gap-3 md:grid-cols-3">
        <ScenarioTile label="Conservative" value={metrics.conservativeValueKes} amount={amount} tone="down" note="Lower band — ~7th percentile" />
        <ScenarioTile label="Expected" value={metrics.expectedValueKes} amount={amount} tone={gain >= 0 ? "up" : "down"} note={`${gain >= 0 ? "+" : ""}${fmtPct(gainPct)} weighted horizon return`} />
        <ScenarioTile label="Optimistic" value={metrics.optimisticValueKes} amount={amount} tone="up" note="Upper band — ~93rd percentile" />
      </div>
      {/* Second row — the "quality" metadata that lets the user judge
          the projection itself, not just the numbers. Sharpe = return
          per unit of risk; MAPE = the model's own error track record. */}
      <div className="mt-3 grid gap-2 sm:grid-cols-3 text-[11px]">
        <div className="rounded border border-seam bg-raised/30 p-2">
          <div className="text-hint uppercase tracking-wider">Sharpe ratio (horizon)</div>
          <div className="mt-0.5 font-mono text-sm text-ink">
            {metrics.sharpeRatio == null ? "—" : metrics.sharpeRatio.toFixed(2)}
          </div>
          <div className="mt-0.5 text-hint">Return per unit of σ vs 10%/yr MMF proxy. &gt;0 = beats MMF risk-adjusted.</div>
        </div>
        <div className="rounded border border-seam bg-raised/30 p-2">
          <div className="text-hint uppercase tracking-wider">Model backtest error</div>
          <div className="mt-0.5 font-mono text-sm text-ink">
            ±{metrics.weightedMapePP.toFixed(1)}pp
          </div>
          <div className="mt-0.5 text-hint">Weighted MAPE at {horizon} — LightGBM's own walk-forward accuracy.</div>
        </div>
        <div className="rounded border border-seam bg-raised/30 p-2">
          <div className="text-hint uppercase tracking-wider">Portfolio σ (horizon)</div>
          <div className="mt-0.5 font-mono text-sm text-ink">
            ±{metrics.portfolioSigmaPct.toFixed(1)}%
          </div>
          <div className="mt-0.5 text-hint">Price-based, correlation-adjusted. Independent of model error.</div>
        </div>
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
            <Link to={`/chart/${h.ticker}`} className="text-sm font-semibold text-ink hover:text-accent">
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

// ─── Save modal ─────────────────────────────────────────────────────────────

// ─── Money-Market Fund fallback card ────────────────────────────────────────
// Shown when either:
//   1. No positively-expected NSE tickers survived the filter, OR
//   2. Picks were made but weighted expected return is still negative.
// Presents the ~10%/yr MMF benchmark as an honest alternative — Kenya
// retail investors have Sanlam / CIC / Zimele MMFs paying similar
// rates. Not a recommendation of a specific product, just the
// benchmark so the user can see the "sit out" option.

const HORIZON_DAYS_MAP: Record<HorizonKey, number> = {
  "1M": 21, "3M": 63, "6M": 126, "9M": 189, "12M": 252,
};

const MmfFallbackCard: FC<{
  amount: number;
  horizon: HorizonKey;
  excluded: Array<{ ticker: string; reason: string }>;
  reason: "none-eligible" | "negative-equity-view";
  equityReturnPct?: number;
}> = ({ amount, horizon, excluded, reason, equityReturnPct }) => {
  const mmf = mmfProjection(amount, HORIZON_DAYS_MAP[horizon]);
  const label = HORIZONS.find(h => h.key === horizon)?.label ?? horizon;
  return (
    <Card className="border-amber-400 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40">
      <h2 className="mb-1 text-sm font-semibold text-amber-900 dark:text-amber-300">
        Consider a Money Market Fund at {label}
      </h2>
      <p className="text-[12px] leading-relaxed text-amber-900 dark:text-amber-300">
        {reason === "none-eligible" && (
          <>
            The model sees no NSE positions with a positive expected return at
            {" "}{label} given today's data. That's a genuine market view — not
            a bug in the Planner.
          </>
        )}
        {reason === "negative-equity-view" && (
          <>
            The equity portfolio below currently projects a
            {" "}{fmtPct(equityReturnPct ?? 0)} return over {label}. A Kenya
            money-market fund at ~10%/yr would return ~{fmtPct(mmf.pctReturn)}
            {" "}over the same period without equity drawdown risk.
          </>
        )}
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <div className="rounded border border-amber-300 dark:border-amber-700 bg-white/40 dark:bg-black/20 p-2">
          <div className="text-[10px] uppercase tracking-wider text-amber-800 dark:text-amber-400">
            MMF projected value
          </div>
          <div className="mt-0.5 font-mono text-lg font-bold text-amber-900 dark:text-amber-200">
            {fmtKes(mmf.expectedValueKes)}
          </div>
          <div className="mt-0.5 text-[10px] text-amber-800 dark:text-amber-400">
            {fmtPct(mmf.pctReturn)} at {label} ({(10).toFixed(1)}%/yr, ~zero drawdown)
          </div>
        </div>
        <div className="rounded border border-amber-300 dark:border-amber-700 bg-white/40 dark:bg-black/20 p-2">
          <div className="text-[10px] uppercase tracking-wider text-amber-800 dark:text-amber-400">
            Providers (Kenya)
          </div>
          <div className="mt-0.5 text-[11px] text-amber-900 dark:text-amber-200">
            Sanlam · CIC · Zimele · Britam
          </div>
          <div className="mt-0.5 text-[10px] text-amber-800 dark:text-amber-400">
            Rates vary; ~10%/yr is representative, not a specific product recommendation.
          </div>
        </div>
        <div className="rounded border border-amber-300 dark:border-amber-700 bg-white/40 dark:bg-black/20 p-2">
          <div className="text-[10px] uppercase tracking-wider text-amber-800 dark:text-amber-400">
            What to try next
          </div>
          <ul className="mt-0.5 space-y-0.5 text-[11px] text-amber-900 dark:text-amber-200">
            <li>· Longer horizon (6M / 12M) — model has more signal at those windows</li>
            <li>· Growth risk profile — accepts more volatility for upside</li>
            <li>· Cash equivalent above until the market view improves</li>
          </ul>
        </div>
      </div>
      {excluded.length > 0 && (
        <details className="mt-3 rounded border border-amber-300/60 dark:border-amber-800/60 bg-white/30 dark:bg-black/10 p-2">
          <summary className="cursor-pointer text-[11px] font-semibold text-amber-900 dark:text-amber-300">
            Why the model rejected {excluded.length} candidates
          </summary>
          <ul className="mt-2 space-y-0.5 text-[11px] text-amber-800 dark:text-amber-400">
            {excluded.slice(0, 15).map(e => (
              <li key={e.ticker}>{e.ticker}: {e.reason}</li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
};

const SaveModal: FC<{
  name: string;
  setName: (v: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
  saving: boolean;
  error: string | null;
}> = ({ name, setName, onConfirm, onCancel, saving, error }) => (
  <div
    className="fixed inset-0 z-[9998] flex items-center justify-center bg-black/40 p-4"
    onClick={onCancel}
  >
    <div
      className="w-full max-w-md rounded-xl border border-rim bg-surface p-5"
      onClick={(e) => e.stopPropagation()}
    >
      <h3 className="mb-2 text-sm font-semibold text-ink">Save portfolio</h3>
      <p className="mb-3 text-[11px] text-hint">
        Saved plans include your inputs, the recommendation snapshot, and your custom
        edits (if any). Owner-only — visible only to your account.
      </p>
      <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wider text-hint">
        Name
      </label>
      <input
        type="text"
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="e.g. My growth plan · Nov 2026"
        className="w-full rounded-md border border-seam bg-canvas px-3 py-2 text-sm text-ink outline-none focus:border-accent"
      />
      {error && (
        <p className="mt-2 text-[11px] text-red-600 dark:text-red-400">{error}</p>
      )}
      <div className="mt-4 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-seam bg-raised/40 px-3 py-1.5 text-xs font-semibold text-sub hover:text-ink"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={saving}
          className="rounded bg-sky-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save portfolio"}
        </button>
      </div>
    </div>
  </div>
);
