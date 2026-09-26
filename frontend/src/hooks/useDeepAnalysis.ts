import { useQuery } from "@tanstack/react-query";
import { collection, getDocs, orderBy, query, limit, FirestoreError } from "firebase/firestore";
import { db } from "../lib/firebase";

export interface DeepEvent {
  date: string
  event: string
  estimated_impact: string
}

export interface DeepAnalysis {
  price_movement_explanation: string
  driver_type: "fundamental" | "sentiment" | "technical" | "corporate_action"
  key_events: DeepEvent[]
  outlook: {
    short_term: string
    medium_term: string
  }
  confidence: number
  generated_at: string
  ticker: string
  date: string
}

// Same benign-error handling as useFinancials — permission-denied and
// not-found collapse into "no data yet" so the UI renders a helpful empty
// state instead of a red "Failed to load analysis" banner. Log the code
// so a real rules regression still shows up in the console.
function isBenignFirestoreError(e: unknown): boolean {
  if (e instanceof FirestoreError) {
    // eslint-disable-next-line no-console
    console.error(`[useDeepAnalysis] ${e.code}: ${e.message}`);
    return e.code === "permission-denied" || e.code === "not-found";
  }
  return false;
}

export function useDeepAnalysis(ticker: string) {
  return useQuery<DeepAnalysis | null>({
    queryKey: ["deep-analysis", ticker],
    queryFn: async () => {
      try {
        const col = collection(db, "deep_analysis", ticker, "dates");
        const snap = await getDocs(query(col, orderBy("__name__", "desc"), limit(1)));
        if (snap.empty) return null;
        return { date: snap.docs[0].id, ...snap.docs[0].data() } as DeepAnalysis;
      } catch (e) {
        if (isBenignFirestoreError(e)) return null;
        throw e;
      }
    },
    enabled: !!ticker,
    staleTime: 1000 * 60 * 60,
  });
}
