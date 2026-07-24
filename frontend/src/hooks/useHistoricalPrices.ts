import { useQuery } from "@tanstack/react-query";
import { ref, query, orderByKey, startAt, endAt, get } from "firebase/database";
import { rtdb } from "../lib/rtdb";

export interface RtdbPricePoint {
  date: string;
  o: number | null;
  h: number | null;
  l: number | null;
  c: number | null;
  v: number | null;
  pc: number | null;
  ch: number | null;
  pch: number | null;
  vv: number | null;
}

export function useHistoricalPrices(
  ticker: string,
  startDate: string,
  endDate: string,
) {
  return useQuery<RtdbPricePoint[]>({
    queryKey: ["rtdb-prices", ticker, startDate, endDate],
    queryFn: async () => {
      const pricesQuery = query(
        ref(rtdb, `prices/${ticker}`),
        orderByKey(),
        startAt(startDate),
        endAt(endDate),
      );
      const snap = await get(pricesQuery);
      if (!snap.exists()) return [];
      const val = snap.val() as Record<string, Omit<RtdbPricePoint, "date">>;
      return Object.entries(val).map(([date, fields]) => ({ date, ...fields }));
    },
    enabled: !!ticker && !!startDate && !!endDate,
    staleTime: 1000 * 60 * 5,
  });
}
