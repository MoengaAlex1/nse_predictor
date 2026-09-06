import type { FC } from "react";
import { Link } from "react-router-dom";
import type { CompanyDoc } from "../../types";
import type { Quote } from "../../services/quotes";

type Props = { companies: CompanyDoc[]; quotes?: Map<string, Quote> };

export const TopSignals: FC<Props> = ({ companies, quotes }) => {
  // Price and change come from the quotes service; only `signal` still comes
  // off the company doc.
  const picks = companies
    .filter(c => c.signal === "BUY" && quotes?.get(c.id)?.close != null)
    .sort((a, b) => (quotes?.get(b.id)?.changePct ?? 0) - (quotes?.get(a.id)?.changePct ?? 0))
    .slice(0, 5);

  return (
    <div className="overflow-hidden rounded-xl border border-rim bg-surface">
      <div className="flex items-center justify-between border-b border-seam/60 px-4 py-2.5">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">Top BUY Signals</p>
        <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
          {picks.length} picks
        </span>
      </div>
      {picks.length === 0 ? (
        <p className="px-4 py-6 text-center text-sm text-muted">No BUY signals</p>
      ) : (
        <ul>
          {picks.map((c, i) => {
            const pct = c.change_pct_today;
            return (
              <li key={c.ticker}>
                <Link
                  to={`/chart/${c.ticker}`}
                  className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-raised/60"
                >
                  <span className="w-4 text-[10px] text-hint">{i + 1}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-ink">{c.short}</p>
                    <p className="font-mono text-[10px] text-muted">{c.ticker}</p>
                  </div>
                  <div className="text-right">
                    {quotes?.get(c.id)?.close != null && (
                      <p className="font-mono text-xs text-sub">KES {quotes.get(c.id)!.close!.toFixed(2)}</p>
                    )}
                    {pct != null && (
                      <p className={`font-mono text-xs font-semibold ${pct >= 0 ? "text-emerald-500" : "text-red-500"}`}>
                        {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                      </p>
                    )}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
