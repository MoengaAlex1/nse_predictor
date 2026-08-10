import { create } from "zustand";

const STORAGE_KEY = "nse.recent_tickers";
const MAX_RECENTS = 8;

function loadFromStorage(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((t): t is string => typeof t === "string") : [];
  } catch {
    return [];
  }
}

function saveToStorage(tickers: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tickers));
  } catch {
    // storage may be unavailable (private mode / quota) — recents are best-effort
  }
}

interface RecentTickersState {
  tickers: string[];
  push: (ticker: string) => void;
  clear: () => void;
}

export const useRecentTickers = create<RecentTickersState>((set, get) => ({
  tickers: loadFromStorage(),
  push: (ticker) => {
    const normalized = ticker.trim().toUpperCase();
    if (!normalized) return;
    const current = get().tickers;
    const next = [normalized, ...current.filter((t) => t !== normalized)].slice(0, MAX_RECENTS);
    saveToStorage(next);
    set({ tickers: next });
  },
  clear: () => {
    saveToStorage([]);
    set({ tickers: [] });
  },
}));
