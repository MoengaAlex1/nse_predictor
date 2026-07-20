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
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, MarketOverviewDoc, EventsDoc, CorporateEvent, FinancialsDoc, MacroDoc } from "../types";

export async function fetchAllCompanies(): Promise<CompanyDoc[]> {
  const snap = await getDocs(collection(db, "companies"));
  return snap.docs.map((d) => ({ id: d.id, ...(d.data() as Omit<CompanyDoc, "id">) }));
}

export async function fetchCompany(safeTicker: string): Promise<CompanyDoc | null> {
  const ref = doc(db, "companies", safeTicker);
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return { id: snap.id, ...(snap.data() as Omit<CompanyDoc, "id">) };
}

export async function fetchLatestSnapshot(safeTicker: string): Promise<SnapshotDoc | null> {
  const ref = collection(db, "companies", safeTicker, "snapshots");
  const q = query(ref, orderBy("__name__", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  const d = snap.docs[0];
  return { run_date: d.id, ...(d.data() as Omit<SnapshotDoc, "run_date">) };
}

export async function fetchLatestTechnicals(safeTicker: string): Promise<TechnicalsDoc | null> {
  const ref = collection(db, "companies", safeTicker, "technicals");
  const q = query(ref, orderBy("__name__", "desc"), limit(1));
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
  const q = query(ref, orderBy("__name__", "desc"), limit(1));
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
