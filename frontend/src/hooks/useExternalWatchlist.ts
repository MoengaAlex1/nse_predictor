import { useQuery } from "@tanstack/react-query";
import { ref, get } from "firebase/database";
import { rtdb } from "../lib/rtdb";

/** Shape of a `watchlist/external/{SYMBOL}` node — written every 30 min
 *  during US market hours by pipeline/scripts/fetch_external_watchlist.py.
 *  All fields nullable so an unknown symbol / failed fetch surfaces
 *  gracefully in the UI instead of throwing.
 */
export interface ExternalQuote {
  last: number | null;
  chg: number | null;
  chg_pct: number | null;
  open?: number | null;
  date?: string;
  updated_at?: string;
  yf_symbol?: string;
  source?: string;
}

/** Fetch every external watchlist symbol in one RTDB round-trip.
 *  Returns a Map keyed by display symbol (SPX, AAPL, USOIL, ...).
 *  Empty map on any read failure — the workstation renders em-dashes
 *  instead of crashing. */
async function fetchExternalWatchlist(): Promise<Map<string, ExternalQuote>> {
  try {
    const snap = await get(ref(rtdb, "watchlist/external"));
    if (!snap.exists()) return new Map();
    const val = snap.val() as Record<string, ExternalQuote>;
    return new Map(Object.entries(val));
  } catch {
    return new Map();
  }
}

/** React-Query wrapper. staleTime matches the workflow cadence (30min)
 *  so the frontend doesn't re-fetch on every tab focus. */
export function useExternalWatchlist() {
  return useQuery<Map<string, ExternalQuote>>({
    queryKey: ["watchlist-external"],
    queryFn: fetchExternalWatchlist,
    staleTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}
