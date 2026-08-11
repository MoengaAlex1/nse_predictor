import { useQuery } from "@tanstack/react-query";
import { fetchAllFinancials, fetchAllFundamentals } from "../lib/firestore";
import type { FinancialsDoc, FundamentalsDoc } from "../types";

// One shot at each collection — cheaper than 61+ per-doc reads. Public read
// rules make this a single anonymous request per collection. Cached 5 min
// so a user tabbing between screener rows and detail pages doesn't refetch.

export function useAllFinancials() {
  return useQuery<Map<string, FinancialsDoc>>({
    queryKey: ["all-financials"],
    queryFn: fetchAllFinancials,
    staleTime: 5 * 60 * 1000,
  });
}

export function useAllFundamentals() {
  return useQuery<Map<string, FundamentalsDoc>>({
    queryKey: ["all-fundamentals"],
    queryFn: fetchAllFundamentals,
    staleTime: 5 * 60 * 1000,
  });
}
