import { useQuery } from "@tanstack/react-query";
import { collection, doc, getDoc, getDocs, orderBy, query, limit, FirestoreError } from "firebase/firestore";
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

// Firestore errors we treat as "no data yet" instead of a transport failure.
// permission-denied means security rules block reads for this ticker (deployment
// gap, not an outage); an empty collection is the same thing as missing data.
// Anything else re-throws so react-query surfaces isError=true.
function isBenignFirestoreError(e: unknown): boolean {
  if (e instanceof FirestoreError) {
    // eslint-disable-next-line no-console
    console.error(`[useFinancials] ${e.code}: ${e.message}`);
    return e.code === "permission-denied" || e.code === "not-found";
  }
  return false;
}

export function useFinancials(ticker: string, period?: string) {
  return useQuery<FinancialPeriod | null>({
    queryKey: ["financials-period", ticker, period ?? "latest"],
    queryFn: async () => {
      try {
        if (period) {
          const docRef = doc(db, "financials", ticker, "periods", period);
          const snap = await getDoc(docRef);
          if (!snap.exists()) return null;
          return { period: snap.id, ...snap.data() } as FinancialPeriod;
        }
        const col = collection(db, "financials", ticker, "periods");
        const q = query(col, orderBy("__name__", "desc"), limit(1));
        const snap = await getDocs(q);
        if (snap.empty) return null;
        return { period: snap.docs[0].id, ...snap.docs[0].data() } as FinancialPeriod;
      } catch (e) {
        if (isBenignFirestoreError(e)) return null;
        throw e;
      }
    },
    enabled: !!ticker,
    staleTime: 1000 * 60 * 60,
  });
}
