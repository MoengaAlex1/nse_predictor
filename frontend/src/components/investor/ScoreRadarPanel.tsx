import type { FC } from "react";

// Placeholder — the six-axis scoring model (Valuation / Health / Growth /
// Profitability / Performance / Earnings) isn't defined yet. A radar chart
// with fabricated scores would be worse than an empty slot, so we hold
// the visual footprint and wire the scoring helper in a follow-up.

const AXES = ["Valuation", "Health", "Growth", "Profitability", "Performance", "Earnings"];

export const ScoreRadarPanel: FC = () => (
  <div className="flex h-full flex-col rounded-xl border border-rim bg-surface p-4">
    <div className="flex items-baseline justify-between">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">Score</h3>
      <span className="rounded-full border border-seam bg-raised px-2 py-0.5 text-[10px] font-semibold text-hint">
        Coming soon
      </span>
    </div>
    <div className="relative mt-2 flex flex-1 items-center justify-center">
      <svg width="140" height="140" viewBox="-70 -70 140 140" aria-hidden="true">
        {[0.33, 0.66, 1].map((r) => (
          <polygon
            key={r}
            points={AXES.map((_, i) => {
              const angle = (Math.PI * 2 * i) / AXES.length - Math.PI / 2;
              const x = Math.cos(angle) * 55 * r;
              const y = Math.sin(angle) * 55 * r;
              return `${x.toFixed(2)},${y.toFixed(2)}`;
            }).join(" ")}
            fill="none"
            stroke="rgb(var(--seam))"
            strokeWidth="0.75"
          />
        ))}
        {AXES.map((_, i) => {
          const angle = (Math.PI * 2 * i) / AXES.length - Math.PI / 2;
          return (
            <line
              key={i}
              x1={0}
              y1={0}
              x2={Math.cos(angle) * 55}
              y2={Math.sin(angle) * 55}
              stroke="rgb(var(--seam))"
              strokeWidth="0.5"
            />
          );
        })}
      </svg>
    </div>
    <div className="mt-2 flex flex-wrap justify-center gap-x-3 gap-y-0.5">
      {AXES.map((label) => (
        <span key={label} className="text-[9px] uppercase tracking-wider text-hint">
          {label}
        </span>
      ))}
    </div>
  </div>
);
