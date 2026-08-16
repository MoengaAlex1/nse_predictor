import type { FC } from "react";

interface Props {
  /** Small caps label above the track. */
  label: string;
  /** Left-anchor value (day's low / 52W low). */
  low: number;
  /** Right-anchor value (day's high / 52W high). */
  high: number;
  /**
   * Position of the primary dot along the track. When null, the track is
   * still rendered so users can see the low/high context, but the dot is
   * hidden — honest handling of the "we don't know the current level" case.
   */
  current: number | null;
  /**
   * Optional secondary marker (day's open, previous close, etc.) drawn as a
   * thin vertical tick behind the primary dot. label appears below the track
   * on the same horizontal position.
   */
  marker?: { label: string; value: number } | null;
  /**
   * Optional right-aligned badge — typically the reporting date for the day
   * range or "% of range" for the 52W slider.
   */
  rightMeta?: string;
  /** Optional currency prefix on the numeric bounds. Defaults to "KES ". */
  currencyPrefix?: string;
}

const fmtNum = (n: number): string => n.toFixed(2);

/**
 * Horizontal low/high band with a primary dot for the current position and
 * an optional secondary tick for another reference point (usually today's
 * Open when this slider is showing the Day Range).
 *
 * The MSN Money template does the same thing — a thin bar with the two
 * bounds as labels and a dot showing where today's price sits — and it
 * makes the "is it near the high or the low" question instant to answer
 * without any comparison math.
 */
export const RangeSlider: FC<Props> = ({
  label,
  low,
  high,
  current,
  marker,
  rightMeta,
  currencyPrefix = "KES ",
}) => {
  // Clamp the position to [0, 100] so a stale current price above the day's
  // high (or below its low — happens when RTDB races ahead of the OHLC bar
  // that's still being built) still lands on-track instead of overflowing.
  const posOrNull = (v: number | null): number | null => {
    if (v == null || high === low) return null;
    const raw = ((v - low) / (high - low)) * 100;
    return Math.max(0, Math.min(100, raw));
  };
  const currentPos = posOrNull(current);
  const markerPos  = posOrNull(marker?.value ?? null);
  const pctOfRange = currentPos != null ? Math.round(currentPos) : null;

  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">
          {label}
        </span>
        {rightMeta && (
          <span className="font-mono text-[10px] text-hint">{rightMeta}</span>
        )}
      </div>

      <div className="flex items-center gap-2">
        <span className="font-mono text-[11px] text-sub whitespace-nowrap">
          {currencyPrefix}{fmtNum(low)}
        </span>

        <div className="relative flex-1 h-1.5 rounded-full bg-raised">
          <div className="absolute inset-0 rounded-full bg-seam/50" />
          {/* Secondary marker (open / prev close) — thin tick behind the dot */}
          {markerPos != null && (
            <div
              className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 rounded bg-muted/70"
              style={{ left: `calc(${markerPos}% - 1px)` }}
              aria-hidden="true"
            />
          )}
          {/* Primary dot — current price / current close */}
          {currentPos != null && (
            <div
              className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rounded-full border-2 border-sky-400 bg-surface shadow"
              style={{ left: `calc(${currentPos}% - 6px)` }}
              aria-hidden="true"
            />
          )}
        </div>

        <span className="font-mono text-[11px] text-sub whitespace-nowrap">
          {currencyPrefix}{fmtNum(high)}
        </span>
      </div>

      <div className="flex items-baseline justify-between text-[10px] text-hint">
        {marker ? (
          <span>
            {marker.label} <span className="font-mono text-sub">{currencyPrefix}{fmtNum(marker.value)}</span>
          </span>
        ) : (
          <span />
        )}
        {pctOfRange != null && (
          <span>{pctOfRange}% of range</span>
        )}
      </div>
    </div>
  );
};
