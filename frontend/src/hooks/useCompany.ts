import { useQuery } from "@tanstack/react-query";
import { fetchCompany, fetchLatestSnapshot, fetchLatestTechnicals } from "../lib/firestore";
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc } from "../types";

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
