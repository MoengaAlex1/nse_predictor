import { useMemo } from "react";
import { useCompanies } from "./useCompanies";
import type { CompanyDoc } from "../types";

// Peers = same-sector companies excluding self, ordered by absolute
// change today so the row surfaces the biggest movers first.
export function usePeers(ticker: string, sector: string | null | undefined, limit = 6): CompanyDoc[] {
  const { data: companies = [] } = useCompanies();
  return useMemo(() => {
    if (!sector) return [];
    const upper = ticker.toUpperCase();
    return companies
      .filter((c) => c.sector === sector && c.ticker.toUpperCase() !== upper)
      .sort((a, b) => Math.abs(b.change_pct_today ?? 0) - Math.abs(a.change_pct_today ?? 0))
      .slice(0, limit);
  }, [companies, ticker, sector, limit]);
}
