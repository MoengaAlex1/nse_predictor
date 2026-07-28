"""
NSE PDF Scraper - Step 1 of 2
Crawls company IR pages to find PDF links (annual reports, results announcements),
downloads them into pipeline/data/pdfs/{safe_ticker}/, and writes a manifest.

Usage:
    python pipeline/scripts/scrape_nse_pdfs.py [--tickers KCB EQTY ...] [--all]

Output:
    pipeline/data/pdfs/<safe_ticker>/<filename>.pdf
    pipeline/data/pdfs/manifest.json
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

PIPELINE_ROOT = Path(__file__).parent.parent
PDF_DIR = PIPELINE_ROOT / "data" / "pdfs"
MANIFEST_FILE = PDF_DIR / "manifest.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Company IR pages - ordered by data quality expected
IR_PAGES: dict[str, dict] = {
    # Banking
    "KCB_NR":   {"url": "https://kcbgroup.com/investor-relations/", "name": "KCB Group"},
    "EQTY_NR":  {"url": "https://equitygroupholdings.com/investor-relations/", "name": "Equity Group Holdings"},
    "COOP_NR":  {"url": "https://www.co-opbank.co.ke/investor-relations/", "name": "Co-operative Bank"},
    "NCBA_NR":  {"url": "https://ke.ncbagroup.com/investor-relations/", "name": "NCBA Group"},
    "ABSA_NR":  {"url": "https://www.absabank.co.ke/investor-relations/", "name": "Absa Bank Kenya"},
    "SBIC_NR":  {"url": "https://www.stanbicbank.co.ke/south-africa/personal/ways-to-bank/investor-relations", "name": "Stanbic Holdings"},
    "IMH_NR":   {"url": "https://www.imbankgroup.com/ke/investor-relations/", "name": "I&M Holdings"},
    "DTK_NR":   {"url": "https://dtbk.dtbafrica.com/investor-relations/", "name": "Diamond Trust Bank"},
    "SCBK_NR":  {"url": "https://www.sc.com/ke/about/investor-relations/", "name": "Standard Chartered Kenya"},
    "FMLY_NR":  {"url": "https://familybank.co.ke/investor-relations/", "name": "Family Bank"},
    "HFCK_NR":  {"url": "https://www.hfgroup.co.ke/investor-relations/", "name": "HF Group"},
    # Telco
    "SCOM_NR":  {"url": "https://www.safaricom.co.ke/investor-relations/financials-and-results", "name": "Safaricom"},
    # Manufacturing
    "EABL_NR":  {"url": "https://www.eabl.com/investors", "name": "East African Breweries"},
    "BAT_NR":   {"url": "https://www.batkenya.com/group/sites/BAT_9RNFLH.nsf/vwPagesWebLive/DOBNFKSP", "name": "BAT Kenya"},
    "BOC_NR":   {"url": "https://boc.co.ke/investor-relations/", "name": "BOC Kenya"},
    "CARB_NR":  {"url": "https://carbacid.com/investor-relations/", "name": "Carbacid Investments"},
    "UNGA_NR":  {"url": "https://unga-group.com/investor-relations/", "name": "Unga Group"},
    # Energy
    "KEGN_NR":  {"url": "https://www.kengen.co.ke/index.php/investor-relations", "name": "KenGen"},
    "KPLC_NR":  {"url": "https://kplc.co.ke/investor-relations", "name": "Kenya Power"},
    "KPC_NR":   {"url": "https://www.kpc.co.ke/investor-relations/", "name": "Kenya Pipeline"},
    "TOTL_NR":  {"url": "https://totalenergies.ke/investor-relations", "name": "TotalEnergies Kenya"},
    # Insurance
    "JUB_NR":   {"url": "https://jubileeinsurance.com/ke/about-jubilee/investor-relations/", "name": "Jubilee Holdings"},
    "KNRE_NR":  {"url": "https://kenyare.co.ke/investor-relations/", "name": "Kenya Re-Insurance"},
    "BRIT_NR":  {"url": "https://ke.britam.com/investor-relations/", "name": "Britam Holdings"},
    "CIC_NR":   {"url": "https://ke.cicinsurancegroup.com/investor-relations/", "name": "CIC Insurance"},
    "LBTY_NR":  {"url": "https://www.libertykenya.co.ke/investor-relations/", "name": "Liberty Kenya"},
    # Investment
    "CTUM_NR":  {"url": "https://centum.co.ke/investor-relations/", "name": "Centum Investment"},
    "NSE_NR":   {"url": "https://www.nse.co.ke/investor-relations/", "name": "Nairobi Securities Exchange"},
    # Commercial
    "NMG_NR":   {"url": "https://www.nationmedia.com/investor-relations/", "name": "Nation Media Group"},
    "KQ_NR":    {"url": "https://www.kenya-airways.com/ke/about-us/investor-relations/", "name": "Kenya Airways"},
    "LKL_NR":   {"url": "https://longhornpublishers.com/investor-relations/", "name": "Longhorn Publishers"},
    "SCAN_NR":  {"url": "https://www.wpp-scangroup.com/investor-relations/", "name": "WPP Scangroup"},
    "SGL_NR":   {"url": "https://www.standardmedia.co.ke/corporate/", "name": "Standard Group"},
    # Agricultural
    "KUKZ_NR":  {"url": "https://www.kakuzi.co.ke/investors/", "name": "Kakuzi"},
    "SASN_NR":  {"url": "https://sasini.co.ke/", "name": "Sasini"},
    # Construction
    "CRWN_NR":  {"url": "https://www.crownpaints.co.ke/investor-relations/", "name": "Crown Paints"},
}

# Keywords that indicate a PDF is a financial results document
RESULTS_KEYWORDS = [
    "annual report", "integrated report", "integrated annual report",
    "audited results", "audited financial", "financial results",
    "financial statements", "interim results", "half year results",
    "half-year results", "quarterly results", "abridged results",
    "earnings release", "results announcement", "group results",
    "fy20", "fy 20", "fy2015", "fy2016", "fy2017", "fy2018", "fy2019",
    "fy2020", "fy2021", "fy2022", "fy2023", "fy2024", "fy2025",
    "full year results", "full-year results",
]

# Keywords that indicate a PDF is NOT useful
SKIP_KEYWORDS = [
    "agm notice", "agm proxy", "agm form", "agm minutes", "agm q",
    "notice of meeting", "polling results",
    "proxy form", "corporate governance", "sustainability", "esg",
    "remuneration", "nomination", "memorandum of association",
    "articles of association", "tariff", "price list", "product guide",
    "brochure", "key facts", "fact sheet", "loan", "mortgage",
    "insurance premium", "terms and conditions", "responsible banking",
    "school code", "complaints", "climate report", "climate-report",
    "integrated climate", "human rights", "policy document",
]


def is_results_pdf(text: str) -> bool:
    # Normalise hyphens/underscores to spaces so "agm-notice" matches "agm notice"
    text_lower = text.lower().replace("-", " ").replace("_", " ")
    if any(skip in text_lower for skip in SKIP_KEYWORDS):
        return False
    return any(kw in text_lower for kw in RESULTS_KEYWORDS)


def safe_filename(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if not name or not name.endswith(".pdf"):
        hash_part = hashlib.md5(url.encode()).hexdigest()[:8]
        name = f"document_{hash_part}.pdf"
    # Sanitise
    name = re.sub(r'[^\w\-_\.]', '_', name)
    return name


def find_pdf_links(page_url: str, session: requests.Session) -> list[dict]:
    """Fetch IR page and return list of PDF links with metadata."""
    try:
        resp = session.get(page_url, timeout=20, allow_redirects=True)
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code} - skipping")
            return []
    except Exception as e:
        print(f"    Error fetching page: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    found: list[dict] = []
    seen_urls: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href:
            continue

        # Resolve relative URLs
        full_url = urljoin(page_url, href)

        # Must end with .pdf or have pdf in query string
        if not (full_url.lower().endswith(".pdf") or "pdf" in full_url.lower()):
            continue

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        link_text = a.get_text(strip=True)
        title_attr = a.get("title", "") or a.get("aria-label", "")
        combined_text = f"{link_text} {title_attr} {full_url}"

        if is_results_pdf(combined_text):
            found.append({
                "url": full_url,
                "link_text": link_text or title_attr or Path(urlparse(full_url).path).name,
            })

    # Also check iframes and embedded objects
    for tag in soup.find_all(["iframe", "embed"], src=True):
        src = tag["src"]
        full_url = urljoin(page_url, src)
        if ".pdf" in full_url.lower() and full_url not in seen_urls:
            seen_urls.add(full_url)
            found.append({"url": full_url, "link_text": "embedded pdf"})

    return found


def download_pdf(url: str, dest: Path, session: requests.Session) -> bool:
    """Download a PDF to dest. Returns True on success."""
    try:
        resp = session.get(url, timeout=60, stream=True, allow_redirects=True)
        if resp.status_code != 200:
            return False
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            # Try to verify it's actually a PDF by reading first 4 bytes
            chunk = next(resp.iter_content(4), b"")
            if not chunk.startswith(b"%PDF"):
                return False
            # Write the chunk + rest
            with open(dest, "wb") as f:
                f.write(chunk)
                for data in resp.iter_content(chunk_size=65536):
                    f.write(data)
            return True

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"      Download error: {e}")
        return False


def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(manifest: dict) -> None:
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def process_ticker(
    safe_ticker: str,
    meta: dict,
    session: requests.Session,
    manifest: dict,
    force: bool = False,
) -> None:
    print(f"\n[{safe_ticker}] {meta['name']}")
    print(f"  IR page: {meta['url']}")

    ticker_dir = PDF_DIR / safe_ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)

    pdf_links = find_pdf_links(meta["url"], session)
    if not pdf_links:
        print("  No results PDFs found on IR page")
        return

    print(f"  Found {len(pdf_links)} results PDF(s)")
    ticker_manifest = manifest.setdefault(safe_ticker, {"name": meta["name"], "files": {}})

    for link in pdf_links:
        filename = safe_filename(link["url"])
        dest = ticker_dir / filename

        if dest.exists() and not force:
            size_kb = dest.stat().st_size // 1024
            print(f"    [skip] {filename} already exists ({size_kb}KB)")
            continue

        print(f"    Downloading: {link['link_text'][:60]}")
        print(f"      URL: {link['url'][:80]}")
        ok = download_pdf(link["url"], dest, session)
        if ok:
            size_kb = dest.stat().st_size // 1024
            print(f"      Saved {size_kb}KB -> {filename}")
            ticker_manifest["files"][filename] = {
                "url": link["url"],
                "link_text": link["link_text"],
                "size_kb": size_kb,
                "extracted": False,
            }
        else:
            print(f"      FAILED to download")
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download NSE company result PDFs")
    parser.add_argument("--tickers", nargs="*", help="Specific safe_tickers to process")
    parser.add_argument("--all", action="store_true", help="Process all companies")
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    args = parser.parse_args()

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    session = requests.Session()
    session.headers.update(HEADERS)

    if args.tickers:
        tickers = {t.upper(): IR_PAGES[t.upper()] for t in args.tickers if t.upper() in IR_PAGES}
    else:
        tickers = IR_PAGES

    print(f"Processing {len(tickers)} companies...")

    for safe_ticker, meta in tickers.items():
        process_ticker(safe_ticker, meta, session, manifest, force=args.force)
        save_manifest(manifest)
        time.sleep(1)

    print(f"\n=== Done ===")
    total_files = sum(len(v.get("files", {})) for v in manifest.values())
    print(f"Total PDFs: {total_files}")
    print(f"Manifest: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
