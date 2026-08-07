import {
  collection,
  doc,
  getDoc,
  getDocs,
  query,
  orderBy,
  limit,
} from "firebase/firestore";
import { db } from "./firebase";
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, MarketOverviewDoc, EventsDoc, CorporateEvent, FinancialsDoc, MacroDoc, IntradayPoint, FundamentalsDoc, NewsItem } from "../types";

// Firestore omits fields that were never written rather than storing an
// explicit null, so raw doc data can carry `undefined` for fields CompanyDoc
// types as `X | null`. Normalize at this boundary so every consumer can rely
// on the type: absent means null, never undefined.
function normalizeCompany(id: string, data: Omit<CompanyDoc, "id">): CompanyDoc {
  return {
    ...data,
    id,
    current_price: data.current_price ?? null,
    change_pct_today: data.change_pct_today ?? null,
    signal: data.signal ?? null,
    price_date: data.price_date ?? null,
    last_updated: data.last_updated ?? null,
    price_status: data.price_status ?? null,
    price_status_date: data.price_status_date ?? null,
  };
}

export async function fetchAllCompanies(): Promise<CompanyDoc[]> {
  const snap = await getDocs(collection(db, "companies"));
  return snap.docs.map((d) => normalizeCompany(d.id, d.data() as Omit<CompanyDoc, "id">));
}

export async function fetchCompany(safeTicker: string): Promise<CompanyDoc | null> {
  const ref = doc(db, "companies", safeTicker);
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return normalizeCompany(snap.id, snap.data() as Omit<CompanyDoc, "id">);
}

// These collections are keyed by date, so "latest" is the highest-sorting doc.
// Order on the date FIELD, never on __name__: Firestore auto-creates
// single-field indexes for ordinary fields, but a descending __name__ order
// needs an explicitly deployed index, and this repo deploys none (firebase.json
// declares RTDB rules only). Ordering by __name__ desc therefore fails at
// runtime with FAILED_PRECONDITION "The query requires an index".

export async function fetchLatestSnapshot(safeTicker: string): Promise<SnapshotDoc | null> {
  const ref = collection(db, "companies", safeTicker, "snapshots");
  // run_date is written alongside the doc id — see run_inference.py.
  const q = query(ref, orderBy("run_date", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  const d = snap.docs[0];
  return { run_date: d.id, ...(d.data() as Omit<SnapshotDoc, "run_date">) };
}

export async function fetchLatestTechnicals(safeTicker: string): Promise<TechnicalsDoc | null> {
  const ref = collection(db, "companies", safeTicker, "technicals");
  // date is embedded by build_technicals_result — see pipeline/src/analysis/technicals.py.
  const q = query(ref, orderBy("date", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  return snap.docs[0].data() as TechnicalsDoc;
}

export async function fetchCorporateEvents(safeTicker: string): Promise<CorporateEvent[]> {
  const ref = doc(db, "events", safeTicker);
  const snap = await getDoc(ref);
  if (!snap.exists()) return [];
  const data = snap.data() as EventsDoc;
  return data.items ?? [];
}

export async function fetchMarketOverview(): Promise<MarketOverviewDoc | null> {
  const ref = collection(db, "market_overview");
  // date mirrors the doc id — see write_market_overview in push_to_firestore.py.
  const q = query(ref, orderBy("date", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  return snap.docs[0].data() as MarketOverviewDoc;
}

export async function fetchFinancials(safeTicker: string): Promise<FinancialsDoc | null> {
  const ref = doc(db, "financials", safeTicker);
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return snap.data() as FinancialsDoc;
}

export async function fetchMacro(): Promise<MacroDoc | null> {
  const ref = doc(db, "macro", "kenya");
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return snap.data() as MacroDoc;
}

export async function fetchIntradayDay(ticker: string, date: string): Promise<IntradayPoint[] | null> {
  const ref = doc(db, "companies", ticker, "intraday", date);
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  const data = snap.data() as { points?: IntradayPoint[] };
  return data.points ?? null;
}

export async function fetchFundamentals(safeTicker: string): Promise<FundamentalsDoc | null> {
  const ref = doc(db, "fundamentals", safeTicker);
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return snap.data() as FundamentalsDoc;
}

export async function fetchNews(safeTicker: string): Promise<NewsItem[]> {
  const ref = collection(db, "news", safeTicker, "items");
  const q = query(ref, orderBy("date", "desc"), limit(50));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<NewsItem, "id">) }));
}
