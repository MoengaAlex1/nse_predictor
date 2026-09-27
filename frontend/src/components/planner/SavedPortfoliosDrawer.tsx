import { useState } from "react";
import type { FC } from "react";
import type { SavedPortfolio } from "../../hooks/useUserPortfolios";
import { fmtKes, fmtPct } from "../../lib/format";

// Phase 4 — user's saved portfolios list. Signed-out users see an
// explainer; signed-in users see their list with load / delete actions.

interface Props {
  isSignedIn: boolean;
  portfolios: SavedPortfolio[];
  isLoading: boolean;
  onLoad: (p: SavedPortfolio) => void;
  onDelete: (id: string) => void;
}

export const SavedPortfoliosDrawer: FC<Props> = ({ isSignedIn, portfolios, isLoading, onLoad, onDelete }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-rim bg-surface">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center justify-between px-4 py-3 text-left"
      >
        <span className="text-sm font-semibold text-ink">
          My saved portfolios {isSignedIn && `(${portfolios.length})`}
        </span>
        <span className="text-[11px] text-hint">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="border-t border-seam px-4 py-3">
          {!isSignedIn && (
            <p className="text-[11px] text-hint">
              Sign in to save portfolios. Every portfolio remembers the amount, horizon,
              risk profile, and both the recommended + your custom holdings.
            </p>
          )}
          {isSignedIn && isLoading && (
            <p className="text-[11px] text-hint">Loading…</p>
          )}
          {isSignedIn && !isLoading && portfolios.length === 0 && (
            <p className="text-[11px] text-hint">
              You haven't saved a portfolio yet. Build one above and click Save.
            </p>
          )}
          {isSignedIn && !isLoading && portfolios.length > 0 && (
            <ul className="space-y-2">
              {portfolios.map(p => (
                <li key={p.id} className="rounded-md border border-seam bg-raised/40 p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-ink">{p.name}</p>
                      <p className="text-[10px] text-hint">
                        {p.inputs.horizon} · {p.inputs.risk} · {fmtKes(p.inputs.amountKes)} ·
                        Saved {p.updated_at ? new Date(p.updated_at).toLocaleDateString("en-GB") : "—"}
                      </p>
                    </div>
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => onLoad(p)}
                        className="rounded border border-accent bg-accent/10 px-2 py-1 text-[11px] font-semibold text-accent hover:bg-accent/20"
                      >
                        Load
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          if (window.confirm(`Delete "${p.name}"?`)) onDelete(p.id);
                        }}
                        className="rounded border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-2 py-1 text-[11px] font-semibold text-red-700 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/60"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  <p className="mt-2 text-[11px] text-sub">
                    Recommended snapshot: {p.recommended.holdings.length} holdings · expected {fmtPct(p.recommended.metrics.expectedReturnPct)} → {fmtKes(p.recommended.metrics.expectedValueKes)}
                    {p.custom && (
                      <>
                        {" "}· <strong>Custom</strong>: {p.custom.holdings.length} holdings · {fmtPct(p.custom.metrics.expectedReturnPct)} → {fmtKes(p.custom.metrics.expectedValueKes)}
                      </>
                    )}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};
