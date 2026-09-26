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

// Any Firestore error collapses to "no data yet" — permission-denied,
// unavailable, failed-precondition and friends are all indistinguishable
// to the user and none of them are recoverable from the frontend. The
// code is logged so real rules regressions and missing indexes still
// surface in DevTools.
function isBenignFirestoreError(e: unknown): boolean {
  if (e instanceof FirestoreError) {
    // eslint-disable-next-line no-console
    console.error(`[useDeepAnalysis] ${e.code}: ${e.message}`);
    return true;
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
