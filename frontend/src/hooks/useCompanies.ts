import { useQuery } from "@tanstack/react-query";
import { fetchAllCompanies } from "../lib/firestore";
import type { CompanyDoc } from "../types";

export function useCompanies() {
  return useQuery<CompanyDoc[]>({
    queryKey: ["companies"],
    queryFn: fetchAllCompanies,
    staleTime: 5 * 60 * 1000,
  });
}
