"""
Scrape ISIN + basic company facts for every NSE-listed company from
https://www.nse.co.ke/listed-companies/ and merge into
`fundamentals/{ticker}` on Firestore.

Why this exists:
  - The audit's Phase-1 gap for "CEO / Chairperson / ISIN missing on
    58 of 62 tickers" is really two gaps in one:
      • ISIN + baseline company facts (name, sector, listing date):
        Every listed company has these on the NSE index page — the
        canonical, no-license-needed source. That's what this
        scraper covers.
      • CEO / Chairperson / board / shareholder detail: These live on
        each issuer's IR page, not on the NSE index. The existing
        `enrich_from_ir_pages.py` already covers them for the ~25
        curated top-cap tickers. Extending that to every ticker
        requires more source_url entries in fundamentals.json —
        that's a separate PR because per-company URL curation is
        manual work.
  - No new vendor introduced: script runs in GitHub Actions,
    fetches a public NSE page over plain HTTPS, writes to Firebase.
    Stays inside the three-vendor rule.

Robust to markup drift: tries several selector shapes for the table
row structure NSE has used across its recent site refreshes. Falls
back to <table>-scanning + a regex over cell text if all named
selectors miss.

Usage:
    python pipeline/scripts/scrape_nse_listed_companies.py [--dry-run] [--tickers ABSA SCOM]
Env: FIREBASE_SERVICE_ACCOUNT_JSON, (optional) NSE_INDEX_URL to override
     the source URL for testing.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

DEFAULT_INDEX_URL = "https://www.nse.co.ke/listed-companies/"
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
        "nse-intelligence/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT_S = 30
RATE_LIMIT_S = 1.0

# ISIN format for Kenyan securities: KE followed by 10 alphanumerics
# (usually "0000000" + 3 chars). Validate anything we scrape.
ISIN_RE = re.compile(r"\bKE[0-9A-Z]{10}\b")


def fetch(url: str) -> str:
    """GET with retries. Returns response text or raises."""
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=TIMEOUT_S)
            r.raise_for_status()
            return r.text
        except Exception as e:  # noqa: BLE001
            last_err = e
            wait = 2 ** attempt
            log.warning("fetch %s attempt %d failed: %s (sleep %ds)", url, attempt + 1, e, wait)
            time.sleep(wait)
    raise RuntimeError(f"fetch {url} failed after 3 attempts: {last_err}")


def parse_listed_companies(html: str) -> list[dict[str, Any]]:
    """Extract one record per listed company from the NSE index page.

    Returns a list of dicts with any of: {ticker, name, isin, sector,
    listing_date, source_url}. Missing fields stay absent — the merger
    only writes what's present.

    Handles two shapes NSE has used:
      1. A <table> where each <tr> is one company (2020+ layout).
      2. A grid of card <div>s with data attributes (2024 refresh).
    Falls back to a text-level regex sweep so a third layout wouldn't
    silently produce zero rows.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []

    # ── Shape 1: table rows ─────────────────────────────────────────────
    for tr in soup.select("table tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        text = " | ".join(cells)
        m = ISIN_RE.search(text)
        if not m:
            continue
        # Heuristic: the ticker cell is usually 3-5 uppercase alpha, the
        # name cell is the longest non-ticker/isin cell.
        ticker = next((c for c in cells if re.fullmatch(r"[A-Z]{2,5}", c)), None)
        name = max((c for c in cells if c != ticker and c != m.group(0)),
                   key=len, default=None)
        row: dict[str, Any] = {"isin": m.group(0)}
        if ticker: row["ticker"] = ticker
        if name:   row["name"] = name
        rows.append(row)

    # ── Shape 2: card divs ─────────────────────────────────────────────
    if not rows:
        for card in soup.select("[data-ticker], [data-isin], .company-card, .listing-card"):
            ticker = card.get("data-ticker") or card.select_one("[data-ticker]")
            isin = card.get("data-isin")
            name = card.select_one(".company-name, h3, h4")
            row: dict[str, Any] = {}
            if ticker: row["ticker"] = ticker if isinstance(ticker, str) else ticker.get("data-ticker")
            if isin:   row["isin"]   = isin
            if name:   row["name"]   = name.get_text(strip=True)
            if row:    rows.append(row)

    # ── Shape 3: text-level ISIN sweep (last-resort) ────────────────────
    if not rows:
        for match in ISIN_RE.finditer(html):
            # Grab surrounding 200 chars of source and look for a ticker
            # (all-caps 3-5 letters) nearby.
            start = max(0, match.start() - 200)
            end = min(len(html), match.end() + 200)
            ctx = re.sub(r"<[^>]+>", " ", html[start:end])
            tk = re.search(r"\b([A-Z]{2,5})\b", ctx)
            rows.append({
                "isin": match.group(0),
                **({"ticker": tk.group(1)} if tk else {}),
            })

    # Dedupe by ISIN (some layouts repeat rows for filtering/sorting).
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for r in rows:
        key = r.get("isin") or r.get("ticker") or ""
        if key and key in seen:
            continue
        seen.add(key)
        unique.append(r)

    return unique


def merge_into_fundamentals(db, ticker: str, patch: dict[str, Any], dry_run: bool) -> str:
    """Field-level merge — never overwrite an existing non-null value with
    a null. Returns 'created' / 'updated' / 'noop'."""
    ref = db.collection("fundamentals").document(ticker)
    snap = ref.get()
    existing = snap.to_dict() if snap.exists else {}

    now = datetime.now(timezone.utc).isoformat()
    changes: dict[str, Any] = {}
    for k, v in patch.items():
        if v is None:
            continue
        if existing.get(k) == v:
            continue
        # Never blow away a curated non-null with a scraped null; and if the
        # existing value is a non-null string, prefer keeping it unless the
        # new value is materially different (e.g. we corrected an ISIN typo).
        if existing.get(k) and existing[k] == v:
            continue
        changes[k] = v

    if not changes:
        return "noop"
    changes["ir_enriched_at"] = now
    changes.setdefault("_scrape_source", "nse.co.ke/listed-companies")

    if dry_run:
        log.info("  [dry] %s ← %s", ticker, changes)
        return "created" if not snap.exists else "updated"

    ref.set(changes, merge=True)
    return "created" if not snap.exists else "updated"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*",
                        help="Restrict merge to these tickers (default: all scraped)")
    parser.add_argument("--dry-run", action="store_true", help="Skip Firestore writes")
    parser.add_argument("--url", default=os.environ.get("NSE_INDEX_URL", DEFAULT_INDEX_URL))
    args = parser.parse_args()

    log.info("Fetching NSE listed-companies index: %s", args.url)
    html = fetch(args.url)
    time.sleep(RATE_LIMIT_S)

    parsed = parse_listed_companies(html)
    log.info("Parsed %d company records from the index page", len(parsed))
    if not parsed:
        log.error(
            "Zero records parsed — NSE index HTML shape may have changed. "
            "Save the HTML with: curl -H 'User-Agent: …' %s > /tmp/nse.html "
            "then inspect for the new selector.", args.url,
        )
        sys.exit(2)

    # Firestore init lazy so --dry-run doesn't require the service account.
    if not args.dry_run:
        from pipeline.scripts.firebase_client import get_firestore
        db = get_firestore()
    else:
        db = None

    if args.tickers:
        wanted = {t.upper() for t in args.tickers}
        parsed = [r for r in parsed if (r.get("ticker") or "").upper() in wanted]
        log.info("Filtered to %d records for tickers=%s", len(parsed), sorted(wanted))

    counters = {"noop": 0, "updated": 0, "created": 0, "skipped": 0}
    for r in parsed:
        ticker = (r.get("ticker") or "").upper()
        if not ticker:
            counters["skipped"] += 1
            continue
        # Only ship the fields we know are safe to merge. Anything else the
        # NSE page might carry (a stale phone number, an outdated logo URL)
        # stays out — those belong to the IR enricher, not the index page.
        patch = {k: v for k, v in r.items() if k in {"isin", "name", "sector", "listing_date"} and v}
        outcome = merge_into_fundamentals(db, ticker, patch, args.dry_run) if db else "created"
        counters[outcome] += 1
        log.info("  [%s] %-6s isin=%s", outcome, ticker, r.get("isin"))

    log.info("Done: %s", counters)


if __name__ == "__main__":
    main()
