import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  collection,
  doc,
  getDocs,
  setDoc,
  deleteDoc,
  serverTimestamp,
} from "firebase/firestore";
import { db } from "../lib/firebase";
import { useAuthStore } from "../store/useAuthStore";
import type { Holding, PortfolioMetrics, HorizonKey, RiskProfile } from "../lib/portfolio";

// Portfolio persistence — users/{uid}/portfolios/{id}. Owner-only R/W
// via firestore.rules. Save captures BOTH the recommended snapshot and
// the user's custom edits so a re-load can show a fair before/after
// even after weeks of universe drift.

export interface SavedPortfolio {
  id: string;
  name: string;
  created_at: string;                 // ISO — serialised on read
  updated_at: string;                 // ISO
  inputs: {
    amountKes: number;
    horizon: HorizonKey;
    risk: RiskProfile;
  };
  recommended: {
    holdings: Holding[];
    metrics: PortfolioMetrics;
  };
  custom?: {
    holdings: Holding[];
    metrics: PortfolioMetrics;
  } | null;
}

function isoOrEmpty(v: unknown): string {
  if (!v) return "";
  if (typeof v === "string") return v;
  // Firestore Timestamp → toDate()
  if (typeof v === "object" && v !== null && "toDate" in v && typeof (v as { toDate: () => Date }).toDate === "function") {
    try { return (v as { toDate: () => Date }).toDate().toISOString(); } catch { return ""; }
  }
  return "";
}

export function useUserPortfolios() {
  const user = useAuthStore((s) => s.user);
  const uid = user?.uid ?? null;
  const qc = useQueryClient();

  const listQuery = useQuery<SavedPortfolio[]>({
    queryKey: ["portfolios", uid],
    enabled: !!uid,
    queryFn: async () => {
      if (!uid) return [];
      const ref = collection(db, "users", uid, "portfolios");
      const snap = await getDocs(ref);
      return snap.docs.map(d => {
        const data = d.data() as Omit<SavedPortfolio, "id" | "created_at" | "updated_at"> & {
          created_at?: unknown;
          updated_at?: unknown;
        };
        return {
          id: d.id,
          name: data.name,
          created_at: isoOrEmpty(data.created_at),
          updated_at: isoOrEmpty(data.updated_at),
          inputs: data.inputs,
          recommended: data.recommended,
          custom: data.custom ?? null,
        };
      })
      // Newest first — Firestore doesn't ordering by server-time by
      // default unless we push it into the query, but we're pulling
      // the whole per-user list (max ~50 in practice) so sorting
      // client-side is cheaper than adding an index.
      .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    },
  });

  const saveMutation = useMutation({
    mutationFn: async (payload: Omit<SavedPortfolio, "id" | "created_at" | "updated_at"> & { id?: string }) => {
      if (!uid) throw new Error("Sign in to save a portfolio.");
      const id = payload.id ?? `p_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
      const ref = doc(db, "users", uid, "portfolios", id);
      const now = serverTimestamp();
      await setDoc(ref, {
        name: payload.name,
        inputs: payload.inputs,
        recommended: payload.recommended,
        custom: payload.custom ?? null,
        updated_at: now,
        // Only stamp created_at on first write. setDoc with merge:true
        // and a conditional would be nicer, but a raw check is fine at
        // our scale — a re-save just overwrites.
        created_at: payload.id ? undefined : now,
      }, { merge: true });
      return id;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolios", uid] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      if (!uid) throw new Error("Sign in required.");
      await deleteDoc(doc(db, "users", uid, "portfolios", id));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolios", uid] });
    },
  });

  return {
    isSignedIn: !!uid,
    portfolios: listQuery.data ?? [],
    isLoading: listQuery.isLoading,
    save: saveMutation.mutateAsync,
    remove: deleteMutation.mutateAsync,
    saving: saveMutation.isPending,
  };
}
