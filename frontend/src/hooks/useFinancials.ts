import { useQuery } from "@tanstack/react-query";
import { collection, getDocs, orderBy, query, limit } from "firebase/firestore";
import { db } from "../lib/firebase";

export interface MetricValue {
  current: number | null;
  prior: number | null;
  yoy_pct: number | null;
  unit: string;
  currency: string;
}

export interface RoeValue {
  current: string | null;
  prior: string | null;
  direction: "increased" | "decreased" | null;
}

export interface FinancialPeriod {
  ticker: string;
  period: string;
  comparison_period: string;
  income_statement: Record<string, MetricValue>;
  per_share: Record<string, MetricValue>;
  balance_sheet: Record<string, MetricValue>;
  cash_flow: Record<string, MetricValue>;
  returns: { annualised_roe: RoeValue };
}

export function useFinancials(ticker: string, period?: string) {
  return useQuery<FinancialPeriod | null>({
    queryKey: ["financials-period", ticker, period ?? "latest"],
    queryFn: async () => {
      const col = collection(db, "financials", ticker, "periods");
      const q = period
        ? query(col, limit(1))
        : query(col, orderBy("__name__", "desc"), limit(1));
      const snap = await getDocs(q);
      if (snap.empty) return null;
      const doc = period
        ? (await getDocs(query(col, limit(1)))).docs[0]
        : snap.docs[0];
      return { period: doc.id, ...doc.data() } as FinancialPeriod;
    },
    enabled: !!ticker,
    staleTime: 1000 * 60 * 60,
  });
}
