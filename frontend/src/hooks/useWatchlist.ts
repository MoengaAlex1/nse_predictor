import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { doc, getDoc, updateDoc, arrayUnion, arrayRemove } from "firebase/firestore";
import { db } from "../lib/firebase";
import { useAuthStore } from "../store/useAuthStore";

// Watchlist lives as an array field on the user doc — see createUserDoc in
// lib/auth.ts. Firestore rules already allow owner-only read/write on
// /users/{uid} (firestore.rules), so no rules change is needed for Phase C.

interface UserDocShape {
  watchlist?: string[];
}

export function useWatchlist() {
  const user = useAuthStore((s) => s.user);
  const uid = user?.uid ?? null;
  const qc = useQueryClient();

  const query = useQuery<string[]>({
    queryKey: ["watchlist", uid],
    queryFn: async () => {
      if (!uid) return [];
      const snap = await getDoc(doc(db, "users", uid));
      if (!snap.exists()) return [];
      const data = snap.data() as UserDocShape;
      return data.watchlist ?? [];
    },
    enabled: !!uid,
    staleTime: 30 * 1000,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["watchlist", uid] });

  const add = useMutation({
    mutationFn: async (ticker: string) => {
      if (!uid) throw new Error("Not authenticated");
      await updateDoc(doc(db, "users", uid), { watchlist: arrayUnion(ticker.toUpperCase()) });
    },
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: async (ticker: string) => {
      if (!uid) throw new Error("Not authenticated");
      await updateDoc(doc(db, "users", uid), { watchlist: arrayRemove(ticker.toUpperCase()) });
    },
    onSuccess: invalidate,
  });

  const tickers = query.data ?? [];

  return {
    tickers,
    isAuthenticated: !!uid,
    isLoading: query.isLoading,
    has: (ticker: string) => tickers.includes(ticker.toUpperCase()),
    add: (ticker: string) => add.mutate(ticker),
    remove: (ticker: string) => remove.mutate(ticker),
    isPending: add.isPending || remove.isPending,
  };
}
