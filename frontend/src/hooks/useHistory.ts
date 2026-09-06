/**
 * Adjusted price history. The only way a component should obtain a series for
 * indicators, returns or the 52-week range.
 */
import { useQuery } from "@tanstack/react-query";
import { getHistory, type Bar } from "../services/quotes";
import { adjustPrices, actionDateIndex } from "../services/corporateActions";
import { useFinancials } from "./useCompany";

/** Fetch window — long enough for a 52-week range plus indicator warm-up. */
export function useAdjustedHistory(ticker: string, from: string, to: string) {
  const { data: financials } = useFinancials(ticker);
  const actions = financials?.corporate_actions;
  return useQuery<Bar[]>({
    // Actions change the series, so they belong in the key.
    queryKey: ["history-adjusted", ticker, from, to, (actions ?? []).length],
    queryFn: async () => {
      const bars = await getHistory(ticker, { from, to }, { actions: actionDateIndex(actions) });
      return adjustPrices(bars, actions);
    },
    enabled: !!ticker && !!from && !!to,
    staleTime: 5 * 60 * 1000,
  });
}
