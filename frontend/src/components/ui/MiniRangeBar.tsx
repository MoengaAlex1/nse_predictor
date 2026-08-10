import type { FC } from "react";

type MiniRangeBarProps = {
  low: number | null;
  high: number | null;
  current: number | null;
  label?: string;
  formatValue?: (v: number) => string;
};

const defaultFmt = (v: number) => v.toFixed(2);

export const MiniRangeBar: FC<MiniRangeBarProps> = ({
  low,
  high,
  current,
  label,
  formatValue = defaultFmt,
}) => {
  const hasData = low != null && high != null && high > low;
  const position =
    hasData && current != null
      ? Math.max(0, Math.min(100, ((current - low) / (high - low)) * 100))
      : null;

  return (
    <div>
      {label && (
        <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
          {label}
        </p>
      )}
      <div className="relative h-1.5 rounded-full bg-raised">
        {hasData && position != null && (
          <div
            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-canvas bg-accent shadow"
            style={{ left: `${position}%` }}
            aria-hidden="true"
          />
        )}
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-hint">
        <span>{low != null ? formatValue(low) : "—"}</span>
        <span>{high != null ? formatValue(high) : "—"}</span>
      </div>
    </div>
  );
};
