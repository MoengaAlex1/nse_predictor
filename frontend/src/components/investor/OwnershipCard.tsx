import { useMemo } from "react";
import type { FC } from "react";
import type { FundamentalsDoc } from "../../types";
import { EM_DASH } from "../../lib/format";

type Props = {
  fundamentals: FundamentalsDoc | null | undefined;
};

const TYPE_STYLE: Record<string, string> = {
  strategic:     "border-emerald-600/40 bg-emerald-500/10 text-emerald-500",
  institutional: "border-sky-600/40 bg-sky-500/10 text-sky-500",
  government:    "border-amber-600/40 bg-amber-500/10 text-amber-500",
  insider:       "border-violet-600/40 bg-violet-500/10 text-violet-500",
  retail:        "border-slate-600/40 bg-slate-500/10 text-slate-400",
  other:         "border-slate-600/40 bg-slate-500/10 text-slate-400",
};

export const OwnershipCard: FC<Props> = ({ fundamentals }) => {
  const holders = useMemo(() => {
    const rows = fundamentals?.major_shareholders ?? [];
    return [...rows].sort((a, b) => (b.stake_pct ?? 0) - (a.stake_pct ?? 0));
  }, [fundamentals?.major_shareholders]);

  const totalTracked = useMemo(() => {
    return holders.reduce((s, h) => s + (h.stake_pct ?? 0), 0);
  }, [holders]);
  const freeFloat = Math.max(0, 100 - totalTracked);

  if (holders.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Ownership
        </p>
        <p className="mt-3 text-xs text-hint">
          No shareholder register published yet. IR enrichment pass will
          populate this from the company's investor-relations page.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Ownership
        </p>
        <span className="font-mono text-[10px] text-hint">
          {holders.length} named holders · free float {freeFloat.toFixed(1)}%
        </span>
      </div>

      {/* Stacked bar visualising the top holders + free-float remainder */}
      <div className="border-b border-seam px-4 py-3">
        <div className="flex h-3 overflow-hidden rounded-full border border-seam bg-canvas">
          {holders.map((h, i) => {
            const pct = h.stake_pct ?? 0;
            if (pct <= 0) return null;
            const cls = TYPE_STYLE[h.type ?? "other"] ?? TYPE_STYLE.other;
            const bg = cls.split(" ").find((c) => c.startsWith("bg-")) ?? "bg-slate-500/10";
            const solid = bg.replace("/10", "");
            return (
              <span
                key={i}
                title={`${h.name} · ${pct.toFixed(1)}%`}
                className={solid}
                style={{ width: `${pct}%` }}
              />
            );
          })}
          {freeFloat > 0 && (
            <span
              title={`Free float · ${freeFloat.toFixed(1)}%`}
              className="bg-slate-700/60"
              style={{ width: `${freeFloat}%` }}
            />
          )}
        </div>
      </div>

      <ul className="max-h-[280px] overflow-y-auto">
        {holders.map((h, i) => (
          <li key={i} className="flex items-center gap-3 border-b border-seam/50 px-4 py-2 last:border-0">
            <span className="w-4 shrink-0 text-right font-mono text-[10px] tabular-nums text-hint">
              {i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-ink">{h.name}</p>
              {h.type && (
                <span
                  className={`mt-0.5 inline-block rounded border px-1.5 text-[9px] font-bold uppercase tracking-wider ${
                    TYPE_STYLE[h.type] ?? TYPE_STYLE.other
                  }`}
                >
                  {h.type}
                </span>
              )}
            </div>
            <span className="w-14 shrink-0 text-right font-mono text-xs font-semibold tabular-nums text-ink">
              {h.stake_pct != null ? `${h.stake_pct.toFixed(2)}%` : EM_DASH}
            </span>
          </li>
        ))}
        {freeFloat > 0 && (
          <li className="flex items-center gap-3 border-t border-seam px-4 py-2 bg-raised/40">
            <span className="w-4 shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs italic text-hint">Free float / unlisted</p>
            </div>
            <span className="w-14 shrink-0 text-right font-mono text-xs font-semibold tabular-nums text-hint">
              {freeFloat.toFixed(1)}%
            </span>
          </li>
        )}
      </ul>
    </div>
  );
};
