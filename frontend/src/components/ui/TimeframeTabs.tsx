import type { FC } from "react";
import { TIMEFRAMES, type TimeframeKey } from "../../lib/timeframe";

type TimeframeTabsProps = {
  value: TimeframeKey;
  onChange: (tf: TimeframeKey) => void;
};

export const TimeframeTabs: FC<TimeframeTabsProps> = ({ value, onChange }) => (
  <div className="flex flex-wrap gap-0.5 rounded-lg border border-rim bg-raised p-0.5">
    {TIMEFRAMES.map((tf) => {
      const active = tf === value;
      return (
        <button
          key={tf}
          type="button"
          onClick={() => onChange(tf)}
          className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
            active
              ? "bg-accent text-white dark:bg-accent/20 dark:text-accent"
              : "text-muted hover:text-ink"
          }`}
        >
          {tf}
        </button>
      );
    })}
  </div>
);
