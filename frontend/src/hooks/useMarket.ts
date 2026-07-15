import { useQuery } from "@tanstack/react-query";
import { fetchMarketOverview } from "../lib/firestore";
import type { MarketOverviewDoc } from "../types";

export function useMarketOverview() {
  return useQuery<MarketOverviewDoc | null>({
    queryKey: ["market_overview"],
    queryFn: fetchMarketOverview,
    staleTime: 5 * 60 * 1000,
  });
}
