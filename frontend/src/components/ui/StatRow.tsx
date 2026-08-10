import type { FC, ReactNode } from "react";

type StatRowProps = {
  label: string;
  value?: ReactNode;
  hint?: string;
  placeholder?: boolean;
};

export const StatRow: FC<StatRowProps> = ({ label, value, hint, placeholder }) => (
  <div className="flex items-baseline justify-between border-b border-seam/60 py-2 last:border-b-0">
    <span className="text-xs text-muted" title={hint}>
      {label}
    </span>
    <span
      className={`font-mono text-sm ${placeholder ? "text-hint" : "font-semibold text-ink"}`}
      title={placeholder ? "Coming soon" : undefined}
    >
      {placeholder ? "—" : (value ?? "—")}
    </span>
  </div>
);
