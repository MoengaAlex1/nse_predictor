import { useQuery } from "@tanstack/react-query";
import { collection, getDocs, orderBy, query, limit } from "firebase/firestore";
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

export function useDeepAnalysis(ticker: string) {
  return useQuery<DeepAnalysis | null>({
    queryKey: ["deep-analysis", ticker],
    queryFn: async () => {
      const col = collection(db, "deep_analysis", ticker, "dates");
      const snap = await getDocs(query(col, orderBy("__name__", "desc"), limit(1)));
      if (snap.empty) return null;
      return { date: snap.docs[0].id, ...snap.docs[0].data() } as DeepAnalysis;
    },
    enabled: !!ticker,
    staleTime: 1000 * 60 * 60,
  });
}
