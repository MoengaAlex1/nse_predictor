"""
NSE announcement scraper — pushes to Firestore news/{ticker}/items/{doc_id}.

Usage:
  cd pipeline && python scripts/scrape_news.py

Idempotent: doc_id = hash(date + title). Re-running never creates duplicates.
Fails gracefully per ticker — one failure does not stop others.
Always exits 0 (best-effort enrichment, not core data).
"""
import sys
import os
import hashlib
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── Firebase init (same pattern as run_inference.py) ──────────────────────────
import firebase_admin
from firebase_admin import credentials, firestore as fs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_SA_KEY = os.environ.get("FIREBASE_SA_KEY_PATH", "firebase-key.json")
if not firebase_admin._apps:
    cred = credentials.Certificate(_SA_KEY)
    firebase_admin.initialize_app(cred)

db = fs.client()

# ── Load company tickers from companies.json ──────────────────────────────────
import json
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "companies.json")
with open(_CONFIG_PATH, encoding="utf-8") as f:
    _COMPANIES = json.load(f)

TICKERS = [c["ticker"].replace(".", "_") for c in _COMPANIES]

# ── Type mappings ──────────────────────────────────────────────────────────────
NSE_TYPE_TO_CATEGORY = {
    "financial_result": "earnings",
    "results":          "earnings",
    "dividend":         "dividend",
    "agm":              "agm",
    "corporate_action": "corporate_action",
    "rights":           "corporate_action",
    "bonus":            "corporate_action",
    "regulatory":       "regulatory",
}


def _infer_category(title: str, raw_type: str) -> str:
    mapped = NSE_TYPE_TO_CATEGORY.get(raw_type.lower(), "general")
    if mapped != "general":
        return mapped
    title_lower = title.lower()
    if any(w in title_lower for w in ("result", "profit", "earnings", "revenue")):
        return "earnings"
    if any(w in title_lower for w in ("dividend", "dps")):
        return "dividend"
    if any(w in title_lower for w in ("agm", "annual general")):
        return "agm"
    if any(w in title_lower for w in ("rights", "bonus", "split")):
        return "corporate_action"
    return "general"


# ── Core functions ─────────────────────────────────────────────────────────────
def make_doc_id(date: str, title: str) -> str:
    """Deterministic doc id: hash(date + title). Safe for Firestore paths."""
    raw = f"{date}:{title.strip().lower()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def parse_announcement(row: dict) -> dict:
    """Convert a raw scraped row to a NewsItem dict."""
    raw_type = row.get("type", "general")
    title = row.get("title", "")
    return {
        "date":       row.get("date", ""),
        "title":      title,
        "category":   _infer_category(title, raw_type),
        "body":       row.get("body", None),
        "url":        row.get("url", None) or None,
        "source":     "scraper",
        "created_at": datetime.utcnow().isoformat(),
    }


def push_item(safe_ticker: str, item: dict) -> None:
    """Write a NewsItem to Firestore news/{ticker}/items/{doc_id}."""
    doc_id = make_doc_id(item["date"], item["title"])
    ref = db.collection("news").document(safe_ticker).collection("items").document(doc_id)
    ref.set(item, merge=True)
    log.info("  pushed %s / %s", safe_ticker, doc_id)


def fetch_nse_announcements(safe_ticker: str) -> list:
    """
    Fetch corporate announcements for one ticker from the NSE announcements page.
    Returns [] on any error — caller proceeds to next ticker.

    NSE page: https://www.nse.co.ke/market-statistics/corporate-announcements/
    Parses HTML table with columns: Date | Company | Subject | Document
    """
    try:
        url = "https://www.nse.co.ke/market-statistics/corporate-announcements/"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table = soup.find("table")
        if not table:
            log.warning("%s: no table found on NSE announcements page", safe_ticker)
            return []

        short = safe_ticker.replace("_NR", "").upper()
        rows = []
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if len(cells) < 3:
                continue
            company_cell = cells[1].get_text(strip=True).upper()
            if short not in company_cell:
                continue
            date_str  = cells[0].get_text(strip=True)
            title_str = cells[2].get_text(strip=True)
            link_tag  = cells[-1].find("a") if len(cells) >= 4 else None
            doc_url   = link_tag["href"] if link_tag and link_tag.get("href") else None
            rows.append({
                "date":  _parse_date(date_str),
                "title": title_str,
                "type":  "general",
                "url":   doc_url,
            })

        log.info("%s: fetched %d announcements from NSE", safe_ticker, len(rows))
        return rows

    except Exception as exc:
        log.warning("%s: fetch failed — %s", safe_ticker, exc)
        return []


def _parse_date(raw: str) -> str:
    """Normalise NSE date string to ISO YYYY-MM-DD. Falls back to today on parse error."""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return datetime.utcnow().strftime("%Y-%m-%d")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    log.info("NSE news scraper starting — %d companies", len(TICKERS))
    pushed_total = 0
    for safe_ticker in TICKERS:
        try:
            rows = fetch_nse_announcements(safe_ticker)
            for row in rows:
                item = parse_announcement(row)
                if not item["title"] or not item["date"]:
                    continue
                push_item(safe_ticker, item)
                pushed_total += 1
        except Exception as exc:
            log.error("%s: unhandled error — %s", safe_ticker, exc)
            continue
    log.info("Done — pushed %d items total", pushed_total)


if __name__ == "__main__":
    main()
