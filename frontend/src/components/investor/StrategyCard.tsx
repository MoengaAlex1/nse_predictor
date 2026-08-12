import type { FC } from "react";
import type { FundamentalsDoc } from "../../types";

type Props = {
  fundamentals: FundamentalsDoc | null | undefined;
};

export const StrategyCard: FC<Props> = ({ fundamentals }) => {
  const priorities = fundamentals?.strategic_priorities ?? [];
  const awards = fundamentals?.awards ?? [];

  if (priorities.length === 0 && awards.length === 0) {
    return null;
  }

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Strategy & Recognition
        </p>
      </div>

      <div className="grid gap-4 p-4 md:grid-cols-2">
        {/* Strategic priorities */}
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-hint">
            Strategic priorities
          </p>
          {priorities.length === 0 ? (
            <p className="text-[11px] italic text-hint">
              None extracted from IR yet.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {priorities.map((p, i) => (
                <li key={i} className="flex gap-2 text-xs text-sub">
                  <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-accent" />
                  <span className="leading-snug">{p}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Awards & recognition */}
        <div>
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-hint">
            Recognition & awards
          </p>
          {awards.length === 0 ? (
            <p className="text-[11px] italic text-hint">
              None on file.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {awards.slice(0, 6).map((a, i) => (
                <li key={i} className="flex items-baseline gap-2 text-xs">
                  {a.year != null && (
                    <span className="w-9 shrink-0 font-mono text-[10px] tabular-nums text-hint">
                      {a.year}
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sub">{a.title}</p>
                    {a.issuer && (
                      <p className="mt-0.5 text-[10px] text-hint">{a.issuer}</p>
                    )}
                  </div>
                </li>
              ))}
              {awards.length > 6 && (
                <li className="pl-[52px] text-[10px] italic text-hint">
                  +{awards.length - 6} more
                </li>
              )}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};
