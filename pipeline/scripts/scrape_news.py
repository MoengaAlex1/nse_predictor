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
import json
import hashlib
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ── Firebase init — matches push_to_firestore.py pattern ─────────────────────
import firebase_admin
from firebase_admin import credentials, firestore as fs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

if not firebase_admin._apps:
    sa_raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    if sa_raw.strip().startswith("{"):
        sa_dict = json.loads(sa_raw)
        cred = credentials.Certificate(sa_dict)
    else:
        # local dev fallback: path to key file
        key_path = os.environ.get("FIREBASE_SA_KEY_PATH", "firebase-key.json")
        cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)

db = fs.client()

# ── Load company tickers from companies.json ──────────────────────────────────
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
        "source":     row.get("source", "scraper"),
        "is_pdf":     row.get("is_pdf", False),
        "pdf_url":    row.get("pdf_url", None),
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


# ── Company IR page scraper ───────────────────────────────────────────────────
COMPANY_IR_URLS: dict[str, str] = {
    "SCOM":  "https://www.safaricom.co.ke/investor-relations/financial-information",
    "KCB":   "https://ke.kcbgroup.com/investor-relations/financial-highlights",
    "EQTY":  "https://equitygroupholdings.com/investor-relations/",
    "COOP":  "https://www.co-opbank.co.ke/investor-relations/",
    "EABL":  "https://www.eabl.com/investor-relations",
    "BAT":   "https://www.bat.com/group/sites/UK__9D9KCY.nsf/vwPagesWebLive/DOBBMNC8",
    "BAMB":  "https://www.bamburi.com/en/investors",
    "NMG":   "https://www.nationmedia.com/investor-relations/",
    "BRIT":  "https://www.britam.com/investor-relations",
    "JUB":   "https://www.jubileeinsurance.com/ke/investor-relations",
    "NCBA":  "https://ke.ncbagroup.com/investor-relations/",
    "ABSA":  "https://www.absa.co.ke/investor-relations/",
}


def fetch_company_ir_news(safe_ticker: str) -> list:
    """Scrape company investor relations page for press releases and results."""
    short = safe_ticker.replace("_NR", "").replace(".NR", "")
    url = COMPANY_IR_URLS.get(short)
    if not url:
        return []
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = []
        for a_tag in soup.find_all("a", href=True):
            text = a_tag.get_text(strip=True)
            if len(text) < 10:
                continue
            if not any(kw in text.lower() for kw in (
                "result", "earning", "profit", "revenue", "dividend",
                "annual", "report", "interim", "half year", "full year"
            )):
                continue
            href = a_tag["href"]
            if not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(url, href)
            is_pdf = href.lower().endswith(".pdf")
            rows.append({
                "date":    datetime.utcnow().strftime("%Y-%m-%d"),
                "title":   text,
                "type":    "general",
                "url":     href,
                "body":    None,
                "is_pdf":  is_pdf,
                "pdf_url": href if is_pdf else None,
                "source":  short.lower() + ".ir",
            })
        log.info("%s: fetched %d IR items", safe_ticker, len(rows))
        return rows[:20]
    except Exception as exc:
        log.warning("%s IR: fetch failed — %s", safe_ticker, exc)
        return []


def fetch_marketscreener_news(short_ticker: str) -> list:
    """Fetch latest news from MarketScreener for a ticker."""
    url = f"https://www.marketscreener.com/quote/stock/{short_ticker}/news/"
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = []
        for article in soup.select("article, .article-item, .news-item"):
            title_el = article.find(["h2", "h3", "a"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            date_el = article.find(["time", ".date"])
            date_str = date_el.get("datetime", "")[:10] if date_el else datetime.utcnow().strftime("%Y-%m-%d")
            link_el = article.find("a", href=True)
            href = link_el["href"] if link_el else url
            if href.startswith("/"):
                href = "https://www.marketscreener.com" + href
            rows.append({
                "date":    date_str or datetime.utcnow().strftime("%Y-%m-%d"),
                "title":   title,
                "type":    "general",
                "url":     href,
                "body":    None,
                "is_pdf":  False,
                "pdf_url": None,
                "source":  "marketscreener",
            })
        log.info("%s: fetched %d MarketScreener items", short_ticker, len(rows))
        return rows[:30]
    except Exception as exc:
        log.warning("%s MarketScreener: fetch failed — %s", short_ticker, exc)
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
        short = safe_ticker.replace("_NR", "")
        try:
            all_rows: list = []
            all_rows += fetch_nse_announcements(safe_ticker)
            all_rows += fetch_company_ir_news(safe_ticker)
            all_rows += fetch_marketscreener_news(short)
            for row in all_rows:
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
