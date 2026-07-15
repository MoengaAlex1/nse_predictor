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
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, MarketOverviewDoc } from "../types";

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
  return snap.docs[0].data() as SnapshotDoc;
}

export async function fetchLatestTechnicals(safeTicker: string): Promise<TechnicalsDoc | null> {
  const ref = collection(db, "companies", safeTicker, "technicals");
  const q = query(ref, orderBy("__name__", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  return snap.docs[0].data() as TechnicalsDoc;
}

export async function fetchMarketOverview(): Promise<MarketOverviewDoc | null> {
  const ref = collection(db, "market_overview");
  const q = query(ref, orderBy("__name__", "desc"), limit(1));
  const snap = await getDocs(q);
  if (snap.empty) return null;
  return snap.docs[0].data() as MarketOverviewDoc;
}
