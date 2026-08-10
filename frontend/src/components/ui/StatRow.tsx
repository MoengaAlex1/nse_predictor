import type { FC, ReactNode } from "react";
import { EM_DASH } from "../../lib/format";

type StatRowProps = {
  label: string;
  value?: ReactNode;
  hint?: string;
  placeholder?: boolean;
};

export const StatRow: FC<StatRowProps> = ({ label, value, hint, placeholder }) => (
  <div className="flex items-baseline justify-between gap-3 border-b border-seam/60 py-1.5 last:border-b-0">
    <span className="truncate text-[11px] text-muted" title={hint}>
      {label}
    </span>
    <span
      className={`shrink-0 font-mono text-xs tabular-nums ${placeholder ? "text-hint" : "font-semibold text-ink"}`}
      title={placeholder ? "Coming soon" : undefined}
    >
      {placeholder ? EM_DASH : (value ?? EM_DASH)}
    </span>
  </div>
);
