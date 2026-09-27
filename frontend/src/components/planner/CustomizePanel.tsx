import { useMemo, useState } from "react";
import type { FC } from "react";
import type { Holding, UniverseTicker } from "../../lib/portfolio";
import { fmtKes } from "../../lib/format";

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
  holdings: Holding[];
  universe: UniverseTicker[];
  onChange: (holdings: Holding[]) => void;
  onReset: () => void;                     // restore recommendation
}

export const CustomizePanel: FC<Props> = ({ amountKes, holdings, universe, onChange, onReset }) => {
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
        <h2 className="text-sm font-semibold text-ink">Customize your portfolio</h2>
        <button
          type="button"
          onClick={onReset}
          className="rounded border border-seam bg-raised/40 px-2 py-1 text-[11px] font-semibold text-sub hover:text-ink"
          title="Discard edits and go back to the system recommendation"
        >
          Reset to recommendation
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-seam text-[10px] uppercase tracking-wider text-muted">
              <th className="py-2 pr-3 text-left">Stock</th>
              <th className="py-2 pr-3 text-right">Weight (%)</th>
              <th className="py-2 pr-3 text-right">Allocation</th>
              <th className="py-2 pr-3 text-right">Shares</th>
              <th className="py-2 pl-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-seam/50">
            {holdings.map(h => (
              <tr key={h.ticker} className="hover:bg-raised/40">
                <td className="py-2 pr-3">
                  <span className="font-semibold text-ink">{h.ticker}</span>
                  <span className="ml-2 text-[11px] text-hint">{h.sector}</span>
                </td>
                <td className="py-2 pr-3 text-right">
                  <input
                    type="number"
                    step={1}
                    min={0}
                    max={100}
                    defaultValue={(h.weight * 100).toFixed(1)}
                    onBlur={(e) => setWeight(h.ticker, Number(e.target.value) || 0)}
                    className="w-20 rounded border border-seam bg-canvas px-2 py-1 text-right font-mono text-sm tabular-nums text-ink outline-none focus:border-accent"
                  />
                </td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-ink">
                  {fmtKes(h.allocationKes)}
                </td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-sub">
                  {h.shares.toLocaleString("en-KE")}
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
            ))}
            {holdings.length === 0 && (
              <tr>
                <td colSpan={5} className="py-4 text-center text-sm text-hint">
                  All holdings removed. Add stocks below or reset to the recommendation.
                </td>
              </tr>
            )}
          </tbody>
          <tfoot>
            <tr className={`border-t border-seam text-[11px] ${overOrUnder ? "text-amber-600 dark:text-amber-400" : "text-muted"}`}>
              <td className="py-2 pr-3 uppercase tracking-wider font-semibold">Total</td>
              <td className="py-2 pr-3 text-right font-mono tabular-nums">
                {(totalWeight * 100).toFixed(1)}%
              </td>
              <td className="py-2 pr-3 text-right font-mono tabular-nums">
                {fmtKes(totalAllocation)}
              </td>
              <td colSpan={2} className="py-2 pl-3 text-right">
                {overOrUnder && (
                  <button
                    type="button"
                    onClick={normalise}
                    className="rounded border border-amber-400 dark:border-amber-700 bg-amber-100 dark:bg-amber-900/40 px-2 py-1 text-[11px] font-semibold text-amber-800 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/70"
                    title="Rescale all weights so they sum to 100% — preserves relative proportions"
                  >
                    Normalise to 100%
                  </button>
                )}
              </td>
            </tr>
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
