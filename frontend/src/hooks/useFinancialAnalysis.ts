import { useQuery } from "@tanstack/react-query";
import { collection, getDocs, orderBy, query, limit } from "firebase/firestore";
import { db } from "../lib/firebase";

export interface FinancialAnalysis {
  summary: string;
  revenue_trend: string;
  profit_trend: string;
  debt_levels: string;
  cash_flow_health: string;
  dividend_history: string;
  key_risks: string[];
  growth_opportunities: string[];
  generated_at: string;
}

export function useFinancialAnalysis(ticker: string) {
  return useQuery<FinancialAnalysis | null>({
    queryKey: ["financials-analysis", ticker],
    queryFn: async () => {
      const col = collection(db, "financials", ticker, "analysis");
      const snap = await getDocs(query(col, orderBy("__name__", "desc"), limit(1)));
      if (snap.empty) return null;
      return snap.docs[0].data() as FinancialAnalysis;
    },
    enabled: !!ticker,
    staleTime: 1000 * 60 * 60,
  });
}
