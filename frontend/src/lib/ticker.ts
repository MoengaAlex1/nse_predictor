// Single source of truth for ticker string handling. Historic data (RTDB,
// Firestore doc ids) uses the "base" form without a .NR/.KE/_NR suffix,
// while the URL bar and some inbound Links have carried the suffixed form
// for years (e.g. /company/ABSA.NR). Two rules across the app:
//
//   1. Every data hook receives the BASE form. Wrap every useParams-derived
//      ticker in toBase() before handing it to a hook.
//   2. Every user-facing route uses the BASE form. Callers building <Link>
//      elements route via /company/${toBase(t)} or /chart/${toBase(t)}.
//      A route-level redirect (see App.tsx) turns any suffixed URL into
//      the canonical base form before the page component mounts.
//
// Exception: the `events/{id}` Firestore collection was seeded with the
// underscored suffix form (ABSA_NR, EQTY_NR, …). Use toEventsId() for
// that one specific read path — nothing else in the codebase should
// touch the suffix.

const SUFFIX_RE = /\.(NR|KE)$/i;
const UNDER_SUFFIX_RE = /_NR$/i;

// Canonical base form: uppercase, no NR/KE suffix. Safe to feed into any
// Firestore doc id (companies/{t}, financials/{t}, snapshots/{t}, …) and
// the RTDB prices/{t} node.
export function toBase(ticker: string): string {
  if (!ticker) return "";
  return ticker.trim().toUpperCase().replace(SUFFIX_RE, "").replace(UNDER_SUFFIX_RE, "");
}

// Events doc id form — legacy underscore suffix. Only the events reader
// should call this.
export function toEventsId(ticker: string): string {
  const base = toBase(ticker);
  return base ? `${base}_NR` : "";
}

// Display form for headers/labels — same as toBase for now, but centralised
// so a future change (e.g. showing "ABSA.NR" when the sector is NR) has
// one place to live.
export function toDisplay(ticker: string): string {
  return toBase(ticker);
}
