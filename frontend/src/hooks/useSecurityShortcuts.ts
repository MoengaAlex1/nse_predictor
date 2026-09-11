import { useEffect } from "react";
import { TIMEFRAMES, type TimeframeKey } from "../lib/timeframe";
import { useWatchlist } from "./useWatchlist";

/**
 * Per-security keyboard shortcuts (phase 1 task 7).
 *   W     toggle the current ticker in the watchlist
 *   1..9  switch chart range, in TIMEFRAMES order
 *
 * All are suppressed while the user is typing, and while a modifier is held so
 * they never shadow browser shortcuts.
 */
export function useSecurityShortcuts(
  ticker: string,
  opts: { onRange?: (tf: TimeframeKey) => void } = {},
) {
  const { has, add, remove, isAuthenticated } = useWatchlist();
  const onRange = opts.onRange;

  useEffect(() => {
    if (!ticker) return;
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing =
        el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (typing || e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "w" || e.key === "W") {
        if (!isAuthenticated) return;   // nothing to toggle when signed out
        e.preventDefault();
        if (has(ticker)) remove(ticker);
        else add(ticker);
        return;
      }

      if (onRange && e.key >= "1" && e.key <= "9") {
        const idx = Number(e.key) - 1;
        const tf = TIMEFRAMES[idx];
        if (tf) {
          e.preventDefault();
          onRange(tf);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ticker, has, add, remove, isAuthenticated, onRange]);
}
