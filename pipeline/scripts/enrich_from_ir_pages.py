"""
Enrich company data from investor-relations page HTML.

For every ticker whose fundamentals.json entry carries a source_url (25
top-cap NSE companies today), this script:

 1. Fetches the IR page HTML (with a real browser User-Agent so we get
    server-rendered content, not a bot-block).
 2. Strips HTML to readable text via BeautifulSoup.
 3. Sends the text to NVIDIA Muse Glimmer 30B with a strict extraction
    schema (tool call) covering employees, CEO, business_description,
    address, industry, listing date, ISIN, and any annual-report /
    financial-statement PDF URLs found on the page.
 4. Writes the results:
      companies/{ticker}    — description, employees, ceo (top-level)
      fundamentals/{ticker} — employees, ceo, industry, address, isin
      financials/{ticker}   — merges any new PDF URLs into announcements
                              (deduped) so the disclosure/extraction
                              pipeline picks them up next run.

Cost: ~10-30K input tokens per IR page × 25 pages ≈ 500K input tokens
per full run. Free on NVIDIA build API. Rate-limited to 1s between
requests.

Usage:
    python pipeline/scripts/enrich_from_ir_pages.py [--dry-run] [--tickers SCOM KCB]
Env: NVIDIA_API_KEY, FIREBASE_SERVICE_ACCOUNT_JSON
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

FUNDAMENTALS_JSON = PIPELINE_ROOT / "config" / "fundamentals.json"

NVIDIA_MODEL = "meta/muse-glimmer-30b"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MAX_HTML_CHARS = 400_000  # ~100K tokens, comfortably under 131K context
MAX_TOKENS = 8192
TIMEOUT_S = 180
RATE_LIMIT_S = 1.5

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SYSTEM_PROMPT = (
    "You are extracting structured company facts from a Nairobi Securities "
    "Exchange listed company's investor-relations webpage. Return only what "
    "you can directly verify from the page text — prefer null over guessing."
)

USER_PROMPT = """
Extract structured facts about this NSE-listed company from its
investor-relations webpage. Use the record_ir_facts function. Rules:
- Numbers: only report what appears on the page. Don't estimate.
- Prefer null / empty arrays over inferred values.
- URLs: only extract PDF links that clearly belong to annual reports,
  audited financial statements, integrated reports, or investor
  presentations. Ignore navigation links, terms & conditions, etc.
- business_description: 2-4 concise sentences summarising what the
  company does — pull from any "About" section on the page.

Investor-relations depth extraction (Phase 2 additions):
- major_shareholders: top holders (usually 5-10) with stake_pct if the
  page publishes a shareholder list. Skip anonymous nominee accounts
  unless they aggregate ≥3%. type = strategic / institutional /
  government / insider / retail / other.
- board_of_directors: full list of directors with their role
  (Chairperson / CEO / CFO / Independent Director / Non-Executive).
  Include appointment_date only if the page states it explicitly.
- business_segments: revenue by segment. If percentages aren't shown
  but segment names are, list segments with revenue_pct = null.
- geographic_exposure: revenue by country / region, same rule.
- strategic_priorities: 3-6 short bullet points from the CEO letter,
  strategy page, or "Vision & Mission" section.
- awards: recent recognitions (last 3-5 years). Year + title + issuer.
- credit_rating: agency (Moody's / Fitch / S&P / GCR) + rating string
  (e.g. "B2") + outlook + as_of date if the page publishes one.
"""

EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "record_ir_facts",
        "description": "Structured facts pulled from a company's IR webpage.",
        "parameters": {
            "type": "object",
            "properties": {
                "business_description": {"type": ["string", "null"]},
                "employees":             {"type": ["integer", "null"]},
                "ceo":                   {"type": ["string", "null"]},
                "chairperson":           {"type": ["string", "null"]},
                "founded_year":          {"type": ["integer", "null"]},
                "listing_date":          {"type": ["string", "null"], "description": "YYYY-MM-DD if available"},
                "isin":                  {"type": ["string", "null"]},
                "industry":              {"type": ["string", "null"]},
                "address":               {"type": ["string", "null"]},
                "website":               {"type": ["string", "null"]},
                "shares_outstanding_mn": {"type": ["number", "null"]},
                "recent_pdfs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url":   {"type": "string"},
                            "kind":  {"type": "string", "enum": ["annual_report", "audited_result", "interim_result", "presentation", "other"]},
                        },
                        "required": ["title", "url", "kind"],
                    },
                },
                # ── Phase 2 IR-depth additions ──────────────────────────────
                "major_shareholders": {
                    "type": "array",
                    "description": "Top 5-10 shareholders published on the page. Empty array if none listed.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":     {"type": "string"},
                            "stake_pct": {"type": ["number", "null"]},
                            "type":     {"type": ["string", "null"], "enum": ["strategic", "institutional", "government", "retail", "insider", "other", None]},
                        },
                        "required": ["name"],
                    },
                },
                "board_of_directors": {
                    "type": "array",
                    "description": "Full board / senior management if published. Empty if not.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":            {"type": "string"},
                            "role":            {"type": "string", "description": "Chairperson / CEO / CFO / Independent Director / Non-Executive"},
                            "appointment_date": {"type": ["string", "null"], "description": "YYYY-MM-DD if the page states it"},
                        },
                        "required": ["name", "role"],
                    },
                },
                "business_segments": {
                    "type": "array",
                    "description": "Revenue-generating business lines. If percentages missing, still list segment names with revenue_pct=null.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name":        {"type": "string"},
                            "revenue_pct": {"type": ["number", "null"]},
                            "description": {"type": ["string", "null"]},
                        },
                        "required": ["name"],
                    },
                },
                "geographic_exposure": {
                    "type": "array",
                    "description": "Revenue by country/region. Same null-if-unknown rule.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "country":     {"type": "string"},
                            "revenue_pct": {"type": ["number", "null"]},
                        },
                        "required": ["country"],
                    },
                },
                "strategic_priorities": {
                    "type": "array",
                    "description": "3-6 short bullets from CEO letter / vision / mission / strategy page.",
                    "items": {"type": "string"},
                },
                "awards": {
                    "type": "array",
                    "description": "Corporate recognitions/awards published on the page (last 3-5y).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "year":   {"type": ["integer", "null"]},
                            "title":  {"type": "string"},
                            "issuer": {"type": ["string", "null"]},
                        },
                        "required": ["title"],
                    },
                },
                "credit_rating": {
                    "type": ["object", "null"],
                    "description": "Sovereign/corporate credit rating if published.",
                    "properties": {
                        "agency":  {"type": "string", "description": "Moody's / Fitch / S&P / GCR"},
                        "rating":  {"type": "string", "description": "e.g. B2, BB-, AA"},
                        "outlook": {"type": ["string", "null"], "enum": ["positive", "stable", "negative", None]},
                        "as_of":   {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    },
                    "required": ["agency", "rating"],
                },
                "extraction_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "notes":                 {"type": "string"},
            },
            "required": ["extraction_confidence"],
        },
    },
}


# ---------------------------------------------------------------------------
# HTML fetching + cleaning
# ---------------------------------------------------------------------------

def fetch_html(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=45, allow_redirects=True)
    except requests.RequestException as exc:
        print(f"    ! fetch error: {exc}")
        return None
    if r.status_code != 200:
        print(f"    ! HTTP {r.status_code}")
        return None
    return r.text


def html_to_text(html: str, base_url: str) -> tuple[str, list[dict]]:
    """Strip HTML tags → readable text, and separately harvest all PDF-looking
    anchor links (title + absolute URL)."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return html[:MAX_HTML_CHARS], []

    soup = BeautifulSoup(html, "html.parser")

    # Kill noise
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()

    # Harvest PDF anchors before we flatten to text
    pdfs = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.lower().endswith(".pdf"):
            continue
        title = a.get_text(strip=True) or a.get("title", "").strip()
        if not title:
            continue
        absolute = urljoin(base_url, href)
        pdfs.append({"title": title[:200], "url": absolute})

    text = soup.get_text(separator="\n", strip=True)
    # Collapse consecutive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:MAX_HTML_CHARS], pdfs


# ---------------------------------------------------------------------------
# NVIDIA extraction
# ---------------------------------------------------------------------------

def extract_via_nvidia(client, text: str, discovered_pdfs: list[dict]) -> dict | None:
    fn_name = EXTRACTION_TOOL["function"]["name"]
    # Give the model the harvested-PDF list as a hint so its recent_pdfs
    # field can validate/curate rather than re-guess.
    pdf_hint = "\n".join(f"- {p['title']}: {p['url']}" for p in discovered_pdfs[:40])
    hint = f"\n\nPDF links found on the page (for validation):\n{pdf_hint}" if pdf_hint else ""

    try:
        response = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{USER_PROMPT}\n\n=== PAGE TEXT ===\n{text}{hint}"},
            ],
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "function", "function": {"name": fn_name}},
            temperature=0.1,
            max_tokens=MAX_TOKENS,
            timeout=TIMEOUT_S,
        )
    except Exception as exc:
        print(f"    ! NVIDIA API error: {type(exc).__name__}: {exc}")
        return None

    msg = response.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None)
    if not tool_calls:
        print(f"    ! no tool call")
        return None
    try:
        return json.loads(tool_calls[0].function.arguments)
    except json.JSONDecodeError as exc:
        print(f"    ! JSON parse error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Firestore writes
# ---------------------------------------------------------------------------

def write_enrichment(db, ticker: str, parsed: dict, discovered_pdfs: list[dict], dry_run: bool) -> dict:
    # Enforce the short-form primary key (SCOM), not "SCOM.NR" / "SCOM_NR".
    # Legacy call sites might still pass a display form; coerce loudly.
    from src.identity import is_short, short_from_display_ticker
    if not is_short(ticker):
        ticker = short_from_display_ticker(ticker)

    now = datetime.now(timezone.utc).isoformat()
    summary = {"companies": 0, "fundamentals": 0, "announcements_added": 0}

    company_updates = {}
    if parsed.get("business_description"):
        company_updates["description"] = parsed["business_description"]
    if parsed.get("employees") is not None:
        company_updates["employees"] = parsed["employees"]
    if parsed.get("ceo"):
        company_updates["ceo"] = parsed["ceo"]
    if company_updates:
        company_updates["ir_enriched_at"] = now
        if not dry_run:
            db.collection("companies").document(ticker).set(company_updates, merge=True)
        summary["companies"] = len(company_updates)

    fund_updates = {"ticker": ticker, "ir_enriched_at": now}
    for k in ("employees", "ceo", "chairperson", "industry", "address", "isin", "listing_date", "founded_year"):
        if parsed.get(k) is not None:
            fund_updates[k] = parsed[k]
    # Phase 2 IR-depth fields — only write when non-empty so we don't
    # clobber an earlier good run's data with an empty extraction.
    for array_key in ("major_shareholders", "board_of_directors",
                      "business_segments", "geographic_exposure",
                      "strategic_priorities", "awards"):
        val = parsed.get(array_key)
        if isinstance(val, list) and len(val) > 0:
            fund_updates[array_key] = val
    if parsed.get("credit_rating"):
        fund_updates["credit_rating"] = parsed["credit_rating"]
    # Only overwrite shares if the model returned one AND we don't already
    # have a curated one (curated = trusted).
    fund_snap = db.collection("fundamentals").document(ticker).get()
    fund_existing = fund_snap.to_dict() if fund_snap.exists else {}
    curated = fund_existing.get("method") == "curated"
    if parsed.get("shares_outstanding_mn") is not None and not curated:
        fund_updates["shares_outstanding_mn"] = parsed["shares_outstanding_mn"]
        fund_updates["method"] = "ir-extracted"
        fund_updates["confidence"] = parsed.get("extraction_confidence", "medium")
    if len(fund_updates) > 2 and not dry_run:  # more than just ticker + ir_enriched_at
        db.collection("fundamentals").document(ticker).set(fund_updates, merge=True)
        summary["fundamentals"] = len(fund_updates) - 2

    # Merge new PDFs into financials/{ticker}.announcements. Use both the
    # model-curated recent_pdfs AND the raw harvested list, deduped by URL.
    fin_ref = db.collection("financials").document(ticker)
    fin_snap = fin_ref.get()
    fin_existing = fin_snap.to_dict() if fin_snap.exists else {}
    existing_ann = fin_existing.get("announcements", [])
    existing_urls = {r.get("url") for r in existing_ann if isinstance(r, dict)}

    all_pdfs = list((parsed.get("recent_pdfs") or []))
    # Also fold in harvested PDFs as generic "other"
    for p in discovered_pdfs[:20]:
        if p["url"] not in {q.get("url") for q in all_pdfs}:
            all_pdfs.append({**p, "kind": "other"})

    fresh_ann = []
    for p in all_pdfs:
        url = p.get("url", "").strip()
        if not url or url in existing_urls:
            continue
        # Guess a doc type from the model's kind field
        kind = p.get("kind", "other")
        doc_type = {
            "annual_report":   "financial_result",
            "audited_result":  "financial_result",
            "interim_result":  "financial_result",
            "presentation":    "presentation",
            "other":           "other",
        }.get(kind, "other")
        # Skip anything that isn't a real financial doc — announcements is
        # meant for financial_result PDFs (audited/interim results).
        if doc_type not in ("financial_result",):
            continue
        fresh_ann.append({
            "date":  datetime.now().date().isoformat(),
            "type":  doc_type,
            "title": p.get("title", ""),
            "url":   url,
            "source": f"ir-page:{urlparse(url).hostname or 'unknown'}",
        })
        existing_urls.add(url)

    if fresh_ann and not dry_run:
        merged = sorted(existing_ann + fresh_ann, key=lambda r: r.get("date", ""), reverse=True)
        fin_ref.set({"announcements": merged}, merge=True)
    summary["announcements_added"] = len(fresh_ann)

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_ir_targets(tickers_filter: set[str] | None) -> list[dict]:
    with open(FUNDAMENTALS_JSON, encoding="utf-8") as fh:
        cfg = json.load(fh)
    targets = []
    for tkr, entry in cfg.items():
        if tkr.startswith("_"):
            continue
        if tickers_filter and tkr not in tickers_filter:
            continue
        url = entry.get("source_url")
        if url:
            targets.append({"ticker": tkr, "url": url})
    return targets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tickers", nargs="*")
    args = parser.parse_args()

    api_key = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    if not api_key or not api_key.startswith("nvapi-"):
        raise SystemExit("NVIDIA_API_KEY not set or invalid")

    from openai import OpenAI
    from scripts.firebase_client import get_firestore

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
    db = get_firestore()

    targets = load_ir_targets({t.upper() for t in args.tickers} if args.tickers else None)
    print(f"Enriching {len(targets)} companies from their IR pages\n")

    totals = {"companies": 0, "fundamentals": 0, "announcements_added": 0, "hits": 0}

    for t in targets:
        tkr, url = t["ticker"], t["url"]
        print(f"=== {tkr} ({url}) ===")
        html = fetch_html(url)
        if not html:
            continue

        text, discovered = html_to_text(html, url)
        print(f"  · page text: {len(text)} chars, {len(discovered)} PDF links harvested")

        parsed = extract_via_nvidia(client, text, discovered)
        if not parsed:
            print(f"  · extraction failed")
            time.sleep(RATE_LIMIT_S)
            continue

        print(
            f"  · employees={parsed.get('employees')}  "
            f"ceo={parsed.get('ceo')}  "
            f"pdfs={len(parsed.get('recent_pdfs', []) or [])}  "
            f"confidence={parsed.get('extraction_confidence')}"
        )

        summary = write_enrichment(db, tkr, parsed, discovered, args.dry_run)
        totals["hits"] += 1
        totals["companies"] += summary["companies"]
        totals["fundamentals"] += summary["fundamentals"]
        totals["announcements_added"] += summary["announcements_added"]

        time.sleep(RATE_LIMIT_S)

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n=== Done === {verb} across {totals['hits']}/{len(targets)} tickers")
    print(f"  companies fields updated:  {totals['companies']}")
    print(f"  fundamentals fields added: {totals['fundamentals']}")
    print(f"  announcements PDFs added:  {totals['announcements_added']}")


if __name__ == "__main__":
    main()
