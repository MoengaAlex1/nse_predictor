"""
Enterprise NSE disclosures pipeline.

Fetches every PDF the NSE WordPress media API publishes, classifies it
per company, extracts as much structured metadata as the title/filename
allows, and writes idempotent updates to Firestore under
financials/{bare_ticker}.

What lands in Firestore
-----------------------
financials/{ticker}.announcements   -> [{date, type, title, url}]
financials/{ticker}.corporate_actions -> [{date, type, title, url}]
financials/{ticker}.dividends        -> [{
    announcement_date: str,        # YYYY-MM-DD, from NSE post date
    ex_date:           str | None, # parsed from title if possible, else None
    payment_date:      None,       # inside PDF only — Option C
    amount_kes:        None,       # inside PDF only — Option C
    type: "interim"|"final"|"special"|"scrip"|"bonus"|"none",
    period:            str | None, # e.g. "FY2024", "H1 2025", "Q1 2025"
    title:             str,
    url:               str,
    source:            "nse.co.ke"
}]

What this deliberately does NOT do
----------------------------------
- Extract per-share amount (requires PDF text extraction — Option C)
- Extract audited annual EPS / revenue / net income (Option C — the existing
  extract_pdf_financials.py + analyze_financials_ai.py path handles this)

Why it's safe to run
--------------------
- Idempotent by URL. Records already present in Firestore are skipped.
- Merges into arrays, never overwrites. Existing hand-curated data survives.
- Uses service-account auth (FIREBASE_SERVICE_ACCOUNT_JSON), CI-compatible.
- Dry-run flag prints planned writes without touching Firestore.

Usage
-----
    python pipeline/scripts/refresh_nse_disclosures.py [--dry-run] [--tickers SCOM KCB]

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET (optional)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

# firebase_admin only imported when we actually need Firestore — offline
# mode skips this so contributors can smoke-test parsing without SA creds.

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COMPANIES_CONFIG = PIPELINE_ROOT / "config" / "companies.json"
NSE_MEDIA_API = "https://www.nse.co.ke/wp-json/wp/v2/media"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nse.co.ke/listed-company-announcements/",
}

# Hand-tuned aliases for tickers whose config `name` field alone won't match
# NSE's various spellings. Each entry ADDS to the auto-generated aliases,
# it doesn't replace them. Keys are BARE tickers (matches Firestore doc IDs).
MANUAL_ALIASES: dict[str, list[str]] = {
    "KCB":   ["kcb group", "kcb bank"],
    "EQTY":  ["equity group", "equity bank"],
    "COOP":  ["co-operative bank", "co-op bank", "cooperative bank"],
    "NCBA":  ["ncba group", "ncba bank"],
    "SBIC":  ["stanbic holdings", "stanbic bank"],
    "IMH":   ["i m group", "i&m group", "i&m holdings", "im holdings"],
    "DTK":   ["diamond trust bank", "dtb kenya"],
    "SCBK":  ["standard chartered bank kenya", "standard chartered kenya"],
    "HFCK":  ["hf group", "housing finance"],
    "SCOM":  ["safaricom"],
    "EABL":  ["east african breweries", "eabl"],
    "BAT":   ["british american tobacco", "bat kenya"],
    "TOTL":  ["totalenergies marketing kenya", "total kenya", "totalenergies marketing"],
    "JUB":   ["jubilee holdings", "jubilee insurance"],
    "KNRE":  ["kenya reinsurance", "kenya re-insurance", "kenya re"],
    "BRIT":  ["britam holdings", "britam"],
    "CIC":   ["cic insurance", "cic group"],
    "CTUM":  ["centum investment", "centum"],
    "NSE":   ["nse plc", "nairobi securities exchange"],
    "KQ":    ["kenya airways"],
    "SCAN":  ["wpp scangroup", "scangroup"],
    "SGL":   ["standard group"],
    "KEGN":  ["kengen"],
    "KPLC":  ["kenya power", "kplc"],
    "KUKZ":  ["kakuzi"],
    "CRWN":  ["crown paints"],
    "LBTY":  ["liberty kenya"],
    "NMG":   ["nation media group"],
}

# Classification keywords — order matters (most specific first)
DIVIDEND_KW = [
    "dividend notice", "dividend payment", "interim dividend", "final dividend",
    "proposed dividend", "dividend declaration", "special dividend",
    "scrip dividend", "dividend and bonus", "dividend book closure",
    "dividend book-closure", "book closure", "book-closure",
]
AGM_KW = [
    "annual general meeting notice", "agm notice", "agm 20",
    "extraordinary general meeting notice", "egm notice",
]
CORPORATE_ACTION_KW = [
    "corporate action", "corporate calendar", "investor calendar",
    "event calendar", "action calendar", "forward calendar",
    "rights issue", "bonus share", "share split", "share consolidation",
    "cautionary statement", "takeover",
]
FINANCIAL_RESULT_KW = [
    "audited result", "audited financial", "audited group result",
    "annual report", "integrated report",
    "financial result", "financial statement", "financial statements",
    "group result", "group financial",
    "interim result", "unaudited result", "unaudited financial",
    "half year", "half-year",
]
SKIP_KW = [
    "tender", "rfp ", "request for proposal", "request for quotation",
    "sustainability report", "esg report", "remuneration",
    "trading halt", "trading suspension",
    "polling results", "agm resolutions", "resolutions passed",
    "agm proxy", "proxy form",
    "kshs mn other disclosures",  # aggregate broker reports, not company filings
    "prospectus", "pre-listing",
    "erp system",
]


# ---------------------------------------------------------------------------
# Ticker map — auto-generated from companies.json + manual aliases
# ---------------------------------------------------------------------------

def load_ticker_map() -> dict[str, list[str]]:
    """Build {BARE_TICKER: [name aliases lowercase]} from config."""
    with open(COMPANIES_CONFIG, encoding="utf-8") as fh:
        cfg = json.load(fh)

    m: dict[str, list[str]] = {}
    for entry in cfg:
        short = entry.get("short", "").strip()
        name = entry.get("name", "").strip().lower()
        if not short or not name:
            continue

        aliases = {name}
        # Strip common corporate suffixes for looser matches
        for suffix in [" plc", " ltd", " limited", " kenya", " (k)", " group", " holdings"]:
            trimmed = name.replace(suffix, "").strip()
            if trimmed and trimmed != name:
                aliases.add(trimmed)
        # Include bare short as a fallback alias (e.g., "SCOM" matches filenames)
        aliases.add(short.lower())

        m[short] = sorted(aliases, key=len, reverse=True)  # longer first

    # Layer manual overrides
    for tkr, extra in MANUAL_ALIASES.items():
        merged = set(m.get(tkr, []))
        merged.update(a.lower() for a in extra)
        m[tkr] = sorted(merged, key=len, reverse=True)

    return m


# ---------------------------------------------------------------------------
# Classification + parsing
# ---------------------------------------------------------------------------

def _norm(fname: str, title: str) -> str:
    return re.sub(r"[^a-z0-9 &-]", " ", (fname + " " + (title or "")).lower())


def classify_pdf(fname: str, title: str) -> str | None:
    norm = _norm(fname, title)
    if any(kw in norm for kw in SKIP_KW):
        return None
    if any(kw in norm for kw in DIVIDEND_KW):
        return "dividend"
    if any(kw in norm for kw in AGM_KW):
        return "agm"
    if any(kw in norm for kw in CORPORATE_ACTION_KW):
        return "corporate_action"
    if any(kw in norm for kw in FINANCIAL_RESULT_KW):
        return "financial_result"
    return None


def match_ticker(fname: str, title: str, ticker_map: dict[str, list[str]]) -> str | None:
    norm = _norm(fname, title)
    for tkr, names in ticker_map.items():
        for name in names:
            if name in norm:
                return tkr
    return None


# --- Dividend metadata parsing ---------------------------------------------

DIV_TYPE_PATTERNS = [
    ("special", ["special dividend"]),
    ("scrip",   ["scrip dividend"]),
    ("bonus",   ["bonus", "bonus share", "bonus issue"]),
    ("interim", ["interim dividend", "interim div"]),
    ("final",   ["final dividend", "final div", "proposed dividend"]),
]

# Period patterns — first match wins. Returns (period_label, iso_date_estimate).
PERIOD_PATTERNS: list[tuple[str, str, str]] = [
    # "For The Year Ended 31-03-2025" or "year ended 31/12/2024"
    (r"year ended\s+(\d{1,2})[-/](\d{1,2})[-/](\d{4})", "FY", "day_month_year"),
    # "H1 2025" / "H1-2025" / "half year 2025"
    (r"\bh1\s*[-]?\s*(\d{4})", "H1", "year_only"),
    (r"half[- ]year\s*[-]?\s*(\d{4})", "H1", "year_only"),
    (r"\bh2\s*[-]?\s*(\d{4})", "H2", "year_only"),
    # "Q1 2025", "Q3 2024"
    (r"\bq([1-4])\s*[-]?\s*(\d{4})", "Q_", "quarter_year"),
    # "FY2024" / "FY 2024" / "FY-24"
    (r"\bfy\s*[-]?\s*(\d{2,4})\b", "FY", "year_short"),
    # "31-12-2024" bare date pattern
    (r"\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b", "FY", "day_month_year"),
]


def parse_dividend_type(text: str) -> str:
    tl = text.lower()
    for label, kws in DIV_TYPE_PATTERNS:
        if any(kw in tl for kw in kws):
            return label
    return "none"


def parse_period(text: str) -> tuple[str | None, str | None]:
    """
    Best-effort extraction of the reporting period referenced in a title.
    Returns (period_label, iso_date_estimate) or (None, None) if nothing matched.
    The iso_date_estimate is used as an ex-date approximation.
    """
    tl = text.lower()
    for pattern, label, mode in PERIOD_PATTERNS:
        m = re.search(pattern, tl)
        if not m:
            continue
        try:
            if mode == "day_month_year":
                day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if not (1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2099):
                    continue
                iso = datetime(year, month, day).date().isoformat()
                return f"{label}{year}", iso
            if mode == "year_only":
                year = int(m.group(1))
                if not (2000 <= year <= 2099):
                    continue
                # H1 → 30-Jun, H2 → 31-Dec
                month, day = (6, 30) if label == "H1" else (12, 31)
                iso = datetime(year, month, day).date().isoformat()
                return f"{label} {year}", iso
            if mode == "quarter_year":
                q = int(m.group(1))
                year = int(m.group(2))
                if not (2000 <= year <= 2099):
                    continue
                month, day = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}[q]
                iso = datetime(year, month, day).date().isoformat()
                return f"Q{q} {year}", iso
            if mode == "year_short":
                yr = m.group(1)
                year = int(yr) if len(yr) == 4 else 2000 + int(yr)
                if not (2000 <= year <= 2099):
                    continue
                return f"FY{year}", datetime(year, 12, 31).date().isoformat()
        except (ValueError, KeyError):
            continue
    return None, None


# ---------------------------------------------------------------------------
# NSE WordPress media fetch
# ---------------------------------------------------------------------------

def fetch_all_media(session: requests.Session, max_pages: int = 200, since_year: int | None = 2015) -> list[dict]:
    """Sweep NSE's WordPress media API for PDFs. Default cap of 200 pages
    (100 items/page → 20K PDFs) covers 2015-present for the aggregate NSE
    feed. Stops early if a page returns items older than `since_year`.
    """
    results: list[dict] = []
    page = 1
    stopped_early = False
    while page <= max_pages:
        url = (
            f"{NSE_MEDIA_API}?media_type=application&per_page=100"
            f"&page={page}&mime_type=application/pdf&orderby=date&order=desc"
        )
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                if resp.status_code == 400:
                    # WP returns 400 when we ask past the last page
                    break
                print(f"  [API] page {page}: HTTP {resp.status_code}")
                break
            items = resp.json()
            if not items:
                break
            results.extend(items)
            # Log the newest+oldest date on this page so we can see how far
            # back the sweep is reaching.
            newest = items[0].get("date", "")[:10] if items else ""
            oldest = items[-1].get("date", "")[:10] if items else ""
            # WordPress exposes total-pages / total-items via response headers;
            # trust that instead of guessing from item count. A page returning
            # 99 instead of 100 items just means the filter dropped one — not
            # that we've hit the end.
            total_pages_header = resp.headers.get("X-WP-TotalPages")
            try:
                total_pages = int(total_pages_header) if total_pages_header else None
            except ValueError:
                total_pages = None
            total_items = resp.headers.get("X-WP-Total") or "?"
            print(f"  [API] page {page}/{total_pages or '?'}: {len(items)} items "
                  f"({newest} → {oldest}), {len(results)} of {total_items} total")

            # Stop when we cross the since_year cutoff so we don't burn API
            # quota fetching pre-2015 PDFs we don't care about.
            if since_year and oldest and oldest[:4].isdigit() and int(oldest[:4]) < since_year:
                stopped_early = True
                break

            # Only stop when the server tells us this was the last page
            # (either via X-WP-TotalPages or by returning zero items).
            if not items:
                break
            if total_pages and page >= total_pages:
                break
            page += 1
            time.sleep(0.3)
        except Exception as exc:
            print(f"  [API] Error page {page}: {exc}")
            break

    if stopped_early:
        print(f"  [API] stopped at page {page} — reached items older than {since_year}")
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_records(all_pdfs: list[dict], ticker_map: dict[str, list[str]]):
    """Return {ticker: {kind: [record, ...]}} where kind is one of
    'dividends', 'corporate_actions', 'announcements'."""
    grouped: dict[str, dict[str, list[dict]]] = {}
    stats = {"skipped_kw": 0, "no_ticker": 0, "no_class": 0, "matched": 0}

    for item in all_pdfs:
        src = item.get("source_url", "")
        if not src or not src.lower().endswith(".pdf"):
            continue

        fname = src.rsplit("/", 1)[-1]
        title_raw = item.get("title", {})
        title = (
            title_raw.get("rendered", "")
            if isinstance(title_raw, dict)
            else str(title_raw)
        )

        doc_type = classify_pdf(fname, title)
        if doc_type is None:
            stats["skipped_kw"] += 1
            continue

        ticker = match_ticker(fname, title, ticker_map)
        if not ticker:
            stats["no_ticker"] += 1
            continue

        stats["matched"] += 1
        date_str = item.get("date", "")[:10]

        if doc_type == "dividend":
            div_type = parse_dividend_type(fname + " " + title)
            period, period_end_iso = parse_period(fname + " " + title)
            # ex_date and amount_kes are NOT derivable from the title/filename
            # alone — they live inside the PDF body. We leave them null here
            # and populate them via a follow-up PDF-extraction pass (Option C).
            # period + period_end give the frontend a useful anchor in the
            # meantime (frontend falls back to period_end → announcement_date).
            record = {
                "announcement_date": date_str,
                "ex_date":           None,
                "payment_date":      None,
                "amount_kes":        None,
                "type":              div_type,
                "period":            period,
                "period_end":        period_end_iso,
                "title":             title,
                "url":               src,
                "source":            "nse.co.ke",
            }
            grouped.setdefault(ticker, {}).setdefault("dividends", []).append(record)
        elif doc_type in ("corporate_action", "agm"):
            record = {"date": date_str, "type": doc_type, "title": title, "url": src}
            grouped.setdefault(ticker, {}).setdefault("corporate_actions", []).append(record)
        else:  # financial_result
            record = {"date": date_str, "type": doc_type, "title": title, "url": src}
            grouped.setdefault(ticker, {}).setdefault("announcements", []).append(record)

    return grouped, stats


def merge_into_firestore(db, grouped: dict[str, dict[str, list[dict]]], dry_run: bool) -> tuple[int, int]:
    """Merge grouped records into financials/{ticker}. Returns (tickers_updated, records_added)."""
    updated_tickers = 0
    records_added = 0

    for tkr in sorted(grouped):
        bucket = grouped[tkr]
        doc_ref = db.collection("financials").document(tkr)
        snap = doc_ref.get()
        existing = snap.to_dict() if snap.exists else {}

        new_updates: dict[str, list[dict]] = {}
        for kind, incoming in bucket.items():
            existing_records = existing.get(kind, [])
            seen_urls = {r.get("url") for r in existing_records if isinstance(r, dict)}
            fresh = [r for r in incoming if r.get("url") not in seen_urls]
            if not fresh:
                continue
            # Dedupe within the fresh set by URL
            seen_local: set[str] = set()
            unique_fresh = []
            for r in fresh:
                u = r.get("url")
                if u in seen_local:
                    continue
                seen_local.add(u)
                unique_fresh.append(r)

            date_key = "announcement_date" if kind == "dividends" else "date"
            merged = sorted(
                existing_records + unique_fresh,
                key=lambda r: r.get(date_key, "") or "",
                reverse=True,
            )
            new_updates[kind] = merged
            records_added += len(unique_fresh)
            print(f"  [{tkr}] +{len(unique_fresh)} {kind} (total {len(merged)})")

        if not new_updates:
            continue

        if dry_run:
            print(f"  [{tkr}] DRY-RUN, not writing")
        else:
            doc_ref.set(new_updates, merge=True)
        updated_tickers += 1

    return updated_tickers, records_added


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh NSE disclosures into Firestore")
    parser.add_argument("--dry-run", action="store_true", help="Connect to Firestore but skip writes")
    parser.add_argument("--offline", action="store_true", help="Skip Firestore entirely — print classification only")
    parser.add_argument("--tickers", nargs="*", help="Filter to specific bare tickers (e.g. SCOM KCB)")
    parser.add_argument("--max-pages", type=int, default=200,
                        help="Cap on WP media API pages to fetch (100 items/page). "
                             "Default 200 covers 2015-present.")
    parser.add_argument("--since-year", type=int, default=2015,
                        help="Stop paging when items older than this year appear. "
                             "Set to 0 or blank to disable cutoff.")
    args = parser.parse_args()

    ticker_map = load_ticker_map()
    if args.tickers:
        want = {t.upper() for t in args.tickers}
        ticker_map = {k: v for k, v in ticker_map.items() if k in want}
        print(f"Filtered to {len(ticker_map)} tickers: {sorted(ticker_map)}")
    else:
        print(f"Loaded {len(ticker_map)} tickers from config + manual aliases")

    session = requests.Session()
    session.headers.update(HTTP_HEADERS)

    print("\nFetching PDFs from NSE WordPress media API...")
    since = args.since_year if args.since_year and args.since_year > 0 else None
    all_pdfs = fetch_all_media(session, max_pages=args.max_pages, since_year=since)
    print(f"Total PDFs fetched: {len(all_pdfs)}\n")

    grouped, stats = build_records(all_pdfs, ticker_map)
    print(
        f"Classification: matched={stats['matched']}, "
        f"skipped_kw={stats['skipped_kw']}, no_ticker={stats['no_ticker']}, no_class={stats['no_class']}"
    )
    print(f"Tickers with new records: {len(grouped)}\n")

    if args.offline:
        # Print per-ticker summary of what WOULD land, no Firestore contact
        for tkr in sorted(grouped):
            summary = ", ".join(f"{k}×{len(v)}" for k, v in sorted(grouped[tkr].items()))
            print(f"  [{tkr}] {summary}")
            # Show one sample dividend record for spot-check
            divs = grouped[tkr].get("dividends", [])
            if divs:
                d = divs[0]
                print(f"    e.g. {d['title'][:70]}")
                print(f"         type={d['type']} period={d['period']} ex_date={d['ex_date']}")
        print(f"\n=== Offline classification done === {len(grouped)} tickers with new records")
        return

    if args.dry_run:
        print("DRY-RUN: connecting to Firestore in read-only mode for diff\n")

    from scripts.firebase_client import get_firestore  # lazy — needs SA creds
    db = get_firestore()
    updated_tickers, records_added = merge_into_firestore(db, grouped, dry_run=args.dry_run)

    verb = "would update" if args.dry_run else "updated"
    print(f"\n=== Done === {verb} {updated_tickers} tickers, added {records_added} records")


if __name__ == "__main__":
    main()
