import { useEffect, useMemo, useState } from "react";
import type { FC } from "react";
import type { Holding, UniverseTicker, HorizonKey } from "../../lib/portfolio";
import { fmtKes } from "../../lib/format";

const HORIZON_LABEL: Record<HorizonKey, string> = {
  "1M": "1 Month", "3M": "3 Months", "6M": "6 Months", "9M": "9 Months", "12M": "1 Year",
};

// Local weight input — controlled so external Reset/Load actually
// refreshes the displayed value, but commits on blur or Enter so a
// user can type intermediate strings ("2", "25", "25.") without
// triggering a full metrics recompute per keystroke.
const WeightInput: FC<{ weight: number; onCommit: (pct: number) => void }> = ({ weight, onCommit }) => {
  const [draft, setDraft] = useState<string>((weight * 100).toFixed(1));
  useEffect(() => {
    setDraft((weight * 100).toFixed(1));
  }, [weight]);
  return (
    <input
      type="number"
      step={1}
      min={0}
      max={100}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => onCommit(Number(draft) || 0)}
      onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
      className="w-20 rounded border border-seam bg-canvas px-2 py-1 text-right font-mono text-sm tabular-nums text-ink outline-none focus:border-accent"
    />
  );
};

// Phase 3 — user editing surface for a recommended portfolio. Every
// mutation calls onChange(newHoldings) so the parent recomputes metrics
// via the same computeMetrics(...) function the recommendation uses.
// No parallel math layer.
//
// Rules of the road:
// - Weights are stored on Holding as 0..1 fractions; the input takes
//   percent for user familiarity and converts on blur.
// - Removing a holding renormalises the remaining weights (their
//   pre-remove proportions preserved).
// - Adding a holding lands at 5% by default (matches MIN_HOLDING in
//   portfolio.ts) — user can bump it right after.
// - "Normalise" button forces sum-to-1 when the user has intentionally
//   over/under-allocated during edits.
// - Every displayed number comes from the parent's `amountKes` prop
//   and the derived holding; no fabricated metrics.

interface Props {
  amountKes: number;
  horizon: HorizonKey;
  holdings: Holding[];
  universe: UniverseTicker[];
  onChange: (holdings: Holding[]) => void;
  onReset: () => void;                     // restore recommendation
  onClose: () => void;                     // hide the panel entirely
}

export const CustomizePanel: FC<Props> = ({ amountKes, horizon, holdings, universe, onChange, onReset, onClose }) => {
  // Per-ticker horizon prediction lookup — used to render an
  // Expected Return column that stays current as the user changes
  // horizon or edits weights.
  const predByTicker = useMemo(() => {
    const m: Record<string, { pctReturn: number; mape: number | null } | null> = {};
    for (const u of universe) {
      const p = u.horizonPredictions?.[horizon];
      m[u.ticker] = p ? { pctReturn: p.pctReturn, mape: p.mape } : null;
    }
    return m;
  }, [universe, horizon]);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");

  const currentTickers = useMemo(() => new Set(holdings.map(h => h.ticker)), [holdings]);
  const totalWeight = holdings.reduce((s, h) => s + h.weight, 0);
  const totalAllocation = holdings.reduce((s, h) => s + h.allocationKes, 0);

  const addable = useMemo(() => {
    const q = pickerQuery.trim().toLowerCase();
    return universe
      .filter(u => !currentTickers.has(u.ticker))
      .filter(u => u.currentPrice != null && u.currentPrice > 0)   // can't own something with no price
      .filter(u => !q
        || u.ticker.toLowerCase().includes(q)
        || (u.name ?? "").toLowerCase().includes(q))
      .slice(0, 12);
  }, [universe, currentTickers, pickerQuery]);

  function setWeight(ticker: string, newWeightPct: number): void {
    // Convert to fraction, clamp to [0, 1], recompute allocation +
    // shares against the SAME amountKes so the row math stays
    // internally consistent even when the sum doesn't normalise to 1.
    const frac = Math.min(1, Math.max(0, newWeightPct / 100));
    const next = holdings.map(h => {
      if (h.ticker !== ticker) return h;
      const alloc = frac * amountKes;
      const shares = h.currentPrice > 0 ? Math.floor(alloc / h.currentPrice) : 0;
      return {
        ...h,
        weight: frac,
        allocationKes: alloc,
        shares,
        cashResidueKes: alloc - shares * h.currentPrice,
      };
    });
    onChange(next);
  }

  function remove(ticker: string): void {
    const remaining = holdings.filter(h => h.ticker !== ticker);
    if (remaining.length === 0) { onChange([]); return; }
    const remainingSum = remaining.reduce((s, h) => s + h.weight, 0);
    if (remainingSum === 0) { onChange(remaining); return; }
    // Renormalise: preserve pre-remove proportions.
    const next = remaining.map(h => rescale(h, h.weight / remainingSum, amountKes));
    onChange(next);
  }

  function add(u: UniverseTicker): void {
    if (!u.currentPrice || u.currentPrice <= 0) return;
    // New holding lands at 5%; existing holdings shrink proportionally
    // to make room so the sum stays at 1.
    const newWeight = 0.05;
    const scale = holdings.length ? (1 - newWeight) / (holdings.reduce((s, h) => s + h.weight, 0) || 1) : 1;
    const rescaled = holdings.map(h => rescale(h, h.weight * scale, amountKes));
    const alloc = newWeight * amountKes;
    const shares = Math.floor(alloc / u.currentPrice);
    const added: Holding = {
      ticker: u.ticker,
      name: u.name,
      sector: u.sector,
      weight: newWeight,
      allocationKes: alloc,
      shares,
      cashResidueKes: alloc - shares * u.currentPrice,
      currentPrice: u.currentPrice,
      reasons: [`Added manually — no automated fitness score applied.`],
    };
    onChange([...rescaled, added]);
    setPickerOpen(false);
    setPickerQuery("");
  }

  function normalise(): void {
    if (holdings.length === 0 || totalWeight === 0) return;
    const next = holdings.map(h => rescale(h, h.weight / totalWeight, amountKes));
    onChange(next);
  }

  const overOrUnder = Math.abs(totalWeight - 1) > 0.005;

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">Customize your portfolio</h2>
          <p className="mt-0.5 text-[11px] text-hint">
            Edit weights, remove holdings, or add other NSE stocks. The metrics
            below update as you type — compare against the recommendation.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            className="rounded border border-seam bg-raised/40 px-2 py-1 text-[11px] font-semibold text-sub hover:text-ink"
            title="Discard edits and go back to the system recommendation"
          >
            Reset to recommendation
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-seam bg-raised/40 px-2 py-1 text-[11px] font-semibold text-sub hover:text-ink"
            title="Close the editor"
          >
            Close editor
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-seam text-[10px] uppercase tracking-wider text-muted">
              <th className="py-2 pr-3 text-left" colSpan={4} />
              <th className="py-2 pr-3 text-right font-semibold text-accent" colSpan={2}>
                Expected @ {HORIZON_LABEL[horizon]}
              </th>
              <th className="py-2 pl-3" />
            </tr>
            <tr className="border-b border-seam text-[10px] uppercase tracking-wider text-muted">
              <th className="py-2 pr-3 text-left">Stock</th>
              <th className="py-2 pr-3 text-right">Weight (%)</th>
              <th className="py-2 pr-3 text-right">Allocation</th>
              <th className="py-2 pr-3 text-right">Shares</th>
              <th className="py-2 pr-3 text-right">Return</th>
              <th className="py-2 pr-3 text-right">Value at horizon</th>
              <th className="py-2 pl-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-seam/50">
            {holdings.map(h => {
              const pred = predByTicker[h.ticker];
              const ret = pred?.pctReturn;
              const val = ret != null ? h.allocationKes * (1 + ret / 100) : h.allocationKes;
              const tone = ret == null ? "text-hint"
                : ret >= 0 ? "text-emerald-700 dark:text-emerald-400"
                : "text-red-700 dark:text-red-400";
              return (
              <tr key={h.ticker} className="hover:bg-raised/40">
                <td className="py-2 pr-3">
                  <span className="font-semibold text-ink">{h.ticker}</span>
                  <span className="ml-2 text-[11px] text-hint">{h.sector}</span>
                </td>
                <td className="py-2 pr-3 text-right">
                  <WeightInput
                    weight={h.weight}
                    onCommit={(pct) => setWeight(h.ticker, pct)}
                  />
                </td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-ink">
                  {fmtKes(h.allocationKes)}
                </td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-sub">
                  {h.shares.toLocaleString("en-KE")}
                </td>
                <td className={`py-2 pr-3 text-right font-mono font-semibold tabular-nums ${tone}`}>
                  {ret == null ? "—" : `${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%`}
                  {pred?.mape != null && (
                    <div className="text-[10px] font-normal text-hint">±{pred.mape.toFixed(1)}pp</div>
                  )}
                </td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-ink">
                  {fmtKes(val)}
                </td>
                <td className="py-2 pl-3 text-right">
                  <button
                    type="button"
                    onClick={() => remove(h.ticker)}
                    className="rounded border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-2 py-1 text-[11px] font-semibold text-red-700 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/60"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            );})}
            {holdings.length === 0 && (
              <tr>
                <td colSpan={7} className="py-4 text-center text-sm text-hint">
                  All holdings removed. Add stocks below or reset to the recommendation.
                </td>
              </tr>
            )}
          </tbody>
          <tfoot>
            {(() => {
              const totalValue = holdings.reduce((s, h) => {
                const pred = predByTicker[h.ticker];
                const ret = pred?.pctReturn ?? 0;
                return s + h.allocationKes * (1 + ret / 100);
              }, 0);
              const totalGain = totalValue - totalAllocation;
              const totalPct = totalAllocation > 0 ? (totalGain / totalAllocation) * 100 : 0;
              const gainTone = totalGain >= 0
                ? "text-emerald-700 dark:text-emerald-400"
                : "text-red-700 dark:text-red-400";
              return (
                <tr className={`border-t-2 border-seam text-[11px] ${overOrUnder ? "text-amber-600 dark:text-amber-400" : "text-ink font-semibold"}`}>
                  <td className="py-2 pr-3 uppercase tracking-wider font-semibold">Total</td>
                  <td className="py-2 pr-3 text-right font-mono tabular-nums">
                    {(totalWeight * 100).toFixed(1)}%
                  </td>
                  <td className="py-2 pr-3 text-right font-mono tabular-nums">
                    {fmtKes(totalAllocation)}
                  </td>
                  <td className="py-2 pr-3" />
                  <td className={`py-2 pr-3 text-right font-mono font-semibold tabular-nums ${gainTone}`}>
                    {totalPct >= 0 ? "+" : ""}{totalPct.toFixed(2)}%
                  </td>
                  <td className="py-2 pr-3 text-right font-mono font-semibold tabular-nums text-ink">
                    {fmtKes(totalValue)}
                    <div className={`text-[10px] font-normal ${gainTone}`}>
                      {totalGain >= 0 ? "+" : ""}{fmtKes(totalGain)}
                    </div>
                  </td>
                  <td className="py-2 pl-3 text-right">
                    {overOrUnder && (
                      <button
                        type="button"
                        onClick={normalise}
                        className="rounded border border-amber-400 dark:border-amber-700 bg-amber-100 dark:bg-amber-900/40 px-2 py-1 text-[11px] font-semibold text-amber-800 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/70"
                        title="Rescale all weights so they sum to 100% — preserves relative proportions"
                      >
                        Normalise
                      </button>
                    )}
                  </td>
                </tr>
              );
            })()}
          </tfoot>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setPickerOpen(v => !v)}
          className="rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20"
        >
          {pickerOpen ? "Close picker" : "+ Add another stock"}
        </button>
        {overOrUnder && (
          <span className="text-[11px] text-amber-600 dark:text-amber-400">
            Weights sum to {(totalWeight * 100).toFixed(1)}%. Metrics scale linearly with total exposure until you normalise.
          </span>
        )}
      </div>

      {pickerOpen && (
        <div className="mt-3 rounded-md border border-seam bg-raised/40 p-2">
          <input
            type="text"
            autoFocus
            value={pickerQuery}
            onChange={(e) => setPickerQuery(e.target.value)}
            placeholder="Search NSE listings by ticker or name…"
            className="w-full rounded border border-seam bg-canvas px-2 py-1.5 text-sm text-ink outline-none focus:border-accent"
          />
          <ul className="mt-2 max-h-64 space-y-0.5 overflow-y-auto">
            {addable.map(u => (
              <li key={u.ticker}>
                <button
                  type="button"
                  onClick={() => add(u)}
                  className="flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-xs text-sub hover:bg-canvas hover:text-ink"
                >
                  <span>
                    <span className="font-semibold text-ink">{u.ticker}</span>{" "}
                    <span className="text-hint">{u.name}</span>{" "}
                    <span className="text-[10px] text-hint">· {u.sector}</span>
                  </span>
                  <span className="font-mono text-[10px] tabular-nums text-hint">
                    KES {u.currentPrice?.toFixed(2)}
                  </span>
                </button>
              </li>
            ))}
            {addable.length === 0 && (
              <li className="px-2 py-2 text-xs text-hint">No matches.</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
};

function rescale(h: Holding, newWeight: number, amountKes: number): Holding {
  const alloc = newWeight * amountKes;
  const shares = h.currentPrice > 0 ? Math.floor(alloc / h.currentPrice) : 0;
  return {
    ...h,
    weight: newWeight,
    allocationKes: alloc,
    shares,
    cashResidueKes: alloc - shares * h.currentPrice,
  };
}
