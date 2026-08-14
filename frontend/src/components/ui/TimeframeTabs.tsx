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
          className={`min-h-[36px] rounded-md px-3 py-1.5 text-xs font-semibold transition-colors sm:min-h-0 sm:px-2.5 sm:py-1 ${
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
