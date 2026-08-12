// Single source of truth for the per-company primary key on the frontend.
//
// The rule (2026-08 refactor):
//
//     Firestore doc-id, RTDB path segment, and CompanyDoc.id are ALL
//     the `short` form — uppercase alphanumeric, no dots or underscores.
//     e.g. "SCOM", "EQTY", "KCB", "IMH".
//
// The `ticker` field ("SCOM.NR") is a DISPLAY alias only. Never use it
// as a Map key or a Firestore doc reference.
//
// Every component that builds a Map(companies -> data) must key by
// `docIdFor(c)` (which is just `c.id`) so a future refactor can't
// re-introduce the "ABSA.NR vs ABSA" mismatch bug.

import type { CompanyDoc } from "../types";

const SHORT_RE = /^[A-Z][A-Z0-9]{0,7}$/;

export function isShort(candidate: string | null | undefined): candidate is string {
  return !!candidate && SHORT_RE.test(candidate);
}

/**
 * Canonical primary key for a company. Returns the value that must be used
 * for Firestore doc-id, RTDB path segment, and any Map key that indexes
 * per-ticker data. Throws in dev if `c.id` is not a valid short form —
 * silent fallback would just restage the bug.
 */
export function docIdFor(c: Pick<CompanyDoc, "id" | "short" | "ticker">): string {
  // Prefer `id` (Firestore doc id) but fall back to `short` if id is empty.
  const candidate = c.id || c.short;
  if (isShort(candidate)) return candidate;

  if (import.meta.env.DEV) {
    // Loud in dev so the offending call site surfaces immediately.
    // eslint-disable-next-line no-console
    console.error(
      `[identity] docIdFor() got non-short key: ticker=${c.ticker ?? "?"} id=${c.id ?? "?"} short=${c.short ?? "?"}`,
    );
  }
  // In prod, return whatever we have rather than crashing the UI.
  return candidate ?? "";
}

/**
 * Recover the short form from a display ticker like "SCOM.NR" or
 * "SCOM_NR". Used by useCompany hooks that get `useParams.ticker` from
 * an old bookmark URL — normal code paths should already have the short
 * form via `c.id`.
 */
export function shortFromDisplayTicker(ticker: string): string {
  if (!ticker) return "";
  let base = ticker.toUpperCase();
  for (const suffix of [".NR", "_NR", ".KE", "_KE"]) {
    if (base.endsWith(suffix)) {
      base = base.slice(0, -suffix.length);
      break;
    }
  }
  return isShort(base) ? base : ticker.toUpperCase();
}
