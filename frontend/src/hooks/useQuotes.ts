/**
 * React-query bindings for the quotes service. Components consume these —
 * never `companies.current_price`, and never a price query of their own.
 */
import { useQuery } from "@tanstack/react-query";
import { getQuote, getQuotes, type Quote } from "../services/quotes";

/** Quotes move once per session; a 5-minute window matches the other hooks. */
const STALE_MS = 5 * 60 * 1000;

export function useQuote(ticker: string | null | undefined) {
  return useQuery<Quote | null>({
    queryKey: ["quote", ticker],
    queryFn: () => getQuote(ticker as string),
    enabled: !!ticker,
    staleTime: STALE_MS,
  });
}

/**
 * Batched quotes keyed by canonical (short) ticker. The key is sorted so a
 * re-ordered ticker list does not miss the cache.
 */
export function useQuotesFor(tickers: string[]) {
  const key = [...tickers].sort();
  return useQuery<Map<string, Quote>>({
    queryKey: ["quotes", key],
    queryFn: () => getQuotes(tickers),
    enabled: tickers.length > 0,
    staleTime: STALE_MS,
  });
}
