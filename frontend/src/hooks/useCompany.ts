import { useQuery } from "@tanstack/react-query";
import { fetchCompany, fetchLatestSnapshot, fetchLatestTechnicals, fetchCorporateEvents, fetchFinancials, fetchMacro, fetchIntradayDay } from "../lib/firestore";
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, CorporateEvent, FinancialsDoc, MacroDoc, IntradayPoint } from "../types";

export function useCompany(safeTicker: string) {
  return useQuery<CompanyDoc | null>({
    queryKey: ["company", safeTicker],
    queryFn: () => fetchCompany(safeTicker),
    enabled: !!safeTicker,
  });
}

export function useLatestSnapshot(safeTicker: string, enabled = true) {
  return useQuery<SnapshotDoc | null>({
    queryKey: ["snapshot", safeTicker],
    queryFn: () => fetchLatestSnapshot(safeTicker),
    enabled: !!safeTicker && enabled,
  });
}

export function useLatestTechnicals(safeTicker: string, enabled = true) {
  return useQuery<TechnicalsDoc | null>({
    queryKey: ["technicals", safeTicker],
    queryFn: () => fetchLatestTechnicals(safeTicker),
    enabled: !!safeTicker && enabled,
  });
}

export function useCorporateEvents(safeTicker: string) {
  return useQuery<CorporateEvent[]>({
    queryKey: ["events", safeTicker],
    queryFn: () => fetchCorporateEvents(safeTicker),
    enabled: !!safeTicker,
  });
}

export function useFinancials(safeTicker: string) {
  return useQuery<FinancialsDoc | null>({
    queryKey: ["financials", safeTicker],
    queryFn: () => fetchFinancials(safeTicker),
    enabled: !!safeTicker,
  });
}

export function useMacro() {
  return useQuery<MacroDoc | null>({
    queryKey: ["macro", "kenya"],
    queryFn: () => fetchMacro(),
    staleTime: 1000 * 60 * 60,
  });
}

export function useIntradayDay(safeTicker: string, date: string, enabled: boolean) {
  return useQuery<IntradayPoint[] | null>({
    queryKey: ["intraday", safeTicker, date],
    queryFn: () => fetchIntradayDay(safeTicker, date),
    enabled: !!safeTicker && !!date && enabled,
    staleTime: 1000 * 60 * 60,
  });
}
