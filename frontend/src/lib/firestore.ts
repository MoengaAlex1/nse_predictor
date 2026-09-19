import {
  collection,
  doc,
  getDoc,
  getDocs,
  query,
  orderBy,
  limit,
} from "firebase/firestore";
import { ref, get } from "firebase/database";
import { db } from "./firebase";
import { rtdb } from "./rtdb";
import type { CompanyDoc, SnapshotDoc, TechnicalsDoc, MarketOverviewDoc, EventsDoc, CorporateEvent, FinancialsDoc, MacroDoc, IntradayPoint, FundamentalsDoc, NewsItem } from "../types";
import { isShort, shortFromDisplayTicker } from "./identity";

// Shape of a `prices_latest/{TICKER}` mirror node — written by
// pipeline/scripts/firebase_rtdb.bulk_write_prices after every batch, so
// the grid views (Home, Companies, Screener, MarketHeatmap) can read one
// value per ticker instead of paying a per-doc Firestore round-trip.
interface PricesLatestNode {
  date: string;
  c: number | null;
  pc: number | null;
  pch: number | null;
  ch: number | null;
  v: number | null;
  /** True when the row is a forward-fill from fill_missing_dates.py, not a
   *  real trading day. UI should render the ticker's tile with a "carried
   *  forward" indicator so users know the value isn't a fresh close. */
  filled?: boolean;
}

/**
 * Fetch every ticker's most recent RTDB row in ONE round-trip. Returns a
 * ticker -> latest-row map keyed by the short id (SCOM, EQTY, ...). Any
 * ticker missing from the mirror (fresh ticker with no daily-update run
 * yet) simply won't appear — callers fall back to Firestore for it.
 */
async function fetchPricesLatestMirror(): Promise<Map<string, PricesLatestNode>> {
  try {
    const snap = await get(ref(rtdb, "prices_latest"));
    if (!snap.exists()) return new Map();
    const val = snap.val() as Record<string, PricesLatestNode>;
    return new Map(Object.entries(val));
  } catch {
    // RTDB unreachable — fall back to Firestore-only.
    return new Map();
  }
}

// Firestore omits fields that were never written rather than storing an
// explicit null, so raw doc data can carry `undefined` for fields CompanyDoc
// types as `X | null`. Normalize at this boundary so every consumer can rely
// on the type: absent means null, never undefined.
//
// Post 2026-08 primary-key refactor: `id` MUST be the short form ("SCOM"),
// never "SCOM.NR" / "SCOM_NR". If a legacy doc slips through we coerce it
// so downstream Map lookups stay consistent — but the migration script
// (pipeline/scripts/migrate_to_short_keys.py) should have cleaned this up
// at the source.
function normalizeCompany(rawId: string, data: Omit<CompanyDoc, "id">): CompanyDoc {
  const id = isShort(rawId) ? rawId : shortFromDisplayTicker(rawId);
  return {
    ...data,
    id,
    // Some legacy docs also carry a mismatched `short` field from an older
    // seeder. Trust `id` (which we just normalized) as the canonical primary
    // key and re-derive `short` from it.
    short: id,
    current_price: data.current_price ?? null,
    change_pct_today: data.change_pct_today ?? null,
    signal: data.signal ?? null,
    price_date: data.price_date ?? null,
    last_updated: data.last_updated ?? null,
  };
}

export async function fetchAllCompanies(): Promise<CompanyDoc[]> {
  // Fetch Firestore companies and the RTDB latest-price mirror concurrently.
  // If the RTDB mirror has a fresher date than Firestore's price_date, we
  // stamp current_price/change_pct_today/price_date/previous close from
  // the mirror onto the CompanyDoc — so Home/Screener/Companies tiles show
  // the same price the CompanyDeepDive chart does (single-channel reads).
  const [snap, mirror] = await Promise.all([
    getDocs(collection(db, "companies")),
    fetchPricesLatestMirror(),
  ]);
  return snap.docs.map((d) => {
    const base = normalizeCompany(d.id, d.data() as Omit<CompanyDoc, "id">);
    const latest = mirror.get(base.id);
    if (!latest) return base;
    // Only override if RTDB is at least as fresh as the Firestore snapshot.
    // Firestore's price_date can be null (bare doc); an RTDB mirror always
    // carries a date, so a null Firestore date always yields to the mirror.
    const fsDate = base.price_date ?? "";
    if (latest.date < fsDate) return base;
    return {
      ...base,
      current_price: latest.c ?? base.current_price,
      change_pct_today: latest.pch ?? base.change_pct_today,
      price_date: latest.date,
      volume_today: latest.v ?? null,
      price_is_filled: latest.filled === true,
    };
  });
}

// Batch collection fetches for the market screener. One round-trip per
// collection instead of N per-doc requests. Rules already allow public
// read on financials/ and fundamentals/.

export async function fetchAllFinancials(): Promise<Map<string, FinancialsDoc>> {
  const snap = await getDocs(collection(db, "financials"));
  const out = new Map<string, FinancialsDoc>();
  snap.docs.forEach((d) => out.set(d.id, d.data() as FinancialsDoc));
  return out;
}

export async function fetchAllFundamentals(): Promise<Map<string, FundamentalsDoc>> {
  const snap = await getDocs(collection(db, "fundamentals"));
  const out = new Map<string, FundamentalsDoc>();
  snap.docs.forEach((d) => out.set(d.id, d.data() as FundamentalsDoc));
  return out;
}

export async function fetchCompany(safeTicker: string): Promise<CompanyDoc | null> {
  // Same single-channel merge as fetchAllCompanies but for one ticker. Home
  // uses fetchAllCompanies, the deep-dive uses fetchCompany, and both should
  // see identical prices — this keeps the two paths symmetric.
  const [snap, mirrorSnap] = await Promise.all([
    getDoc(doc(db, "companies", safeTicker)),
    get(ref(rtdb, `prices_latest/${safeTicker}`)).catch(() => null),
  ]);
  if (!snap.exists()) return null;
  const base = normalizeCompany(snap.id, snap.data() as Omit<CompanyDoc, "id">);
  const latest = mirrorSnap?.exists()
    ? (mirrorSnap.val() as PricesLatestNode)
    : null;
  if (!latest) return base;
  const fsDate = base.price_date ?? "";
  if (latest.date < fsDate) return base;
  return {
    ...base,
    current_price: latest.c ?? base.current_price,
    change_pct_today: latest.pch ?? base.change_pct_today,
    price_date: latest.date,
  };
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

/** Fetch the last N snapshots for a ticker, newest first. Powers the
 *  rolling-accuracy panel — each snapshot carries the model's prediction
 *  for `next_trading_day`, which the frontend compares against the
 *  actual RTDB close on that day. */
export async function fetchRecentSnapshots(
  safeTicker: string,
  n: number = 60,
): Promise<SnapshotDoc[]> {
  const ref = collection(db, "companies", safeTicker, "snapshots");
  const q = query(ref, orderBy("run_date", "desc"), limit(n));
  const snap = await getDocs(q);
  return snap.docs.map((d) => ({
    run_date: d.id,
    ...(d.data() as Omit<SnapshotDoc, "run_date">),
  }));
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
