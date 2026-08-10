import { useQueries } from "@tanstack/react-query";
import { ref, query, orderByKey, startAt, endAt, get } from "firebase/database";
import { rtdb } from "../lib/rtdb";
import { cleanTicker } from "../lib/timeframe";
import type { RtdbPricePoint } from "./useHistoricalPrices";

export interface CompareSeries {
  ticker: string;
  points: RtdbPricePoint[];
  isLoading: boolean;
  isError: boolean;
}

// Fans out to N parallel RTDB fetches through TanStack useQueries. Reuses the
// same queryKey shape as useHistoricalPrices so a ticker fetched once elsewhere
// (e.g. the primary via useHistoricalPrices) hits the same cache entry and
// doesn't re-fire.
export function useCompareSeries(
  tickers: string[],
  startDate: string,
  endDate: string,
): CompareSeries[] {
  const results = useQueries({
    queries: tickers.map((t) => {
      const cleaned = cleanTicker(t);
      return {
        queryKey: ["rtdb-prices", cleaned, startDate, endDate],
        queryFn: async (): Promise<RtdbPricePoint[]> => {
          const q = query(
            ref(rtdb, `prices/${cleaned}`),
            orderByKey(),
            startAt(startDate),
            endAt(endDate),
          );
          const snap = await get(q);
          if (!snap.exists()) return [];
          const val = snap.val() as Record<string, Omit<RtdbPricePoint, "date">>;
          return Object.entries(val).map(([date, fields]) => ({ date, ...fields }));
        },
        enabled: !!t && !!startDate && !!endDate,
        staleTime: 1000 * 60 * 5,
      };
    }),
  });

  return results.map((r, i) => ({
    ticker: tickers[i],
    points: (r.data ?? []) as RtdbPricePoint[],
    isLoading: r.isLoading,
    isError: r.isError,
  }));
}
