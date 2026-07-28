"""
NSE WordPress API PDF Downloader
Fetches financial result PDFs directly from the NSE website's WordPress media API.
Maps PDFs to our tracked tickers by company name matching.

Usage:
    python pipeline/scripts/scrape_nse_wp_api.py [--all] [--tickers KCB_NR ...]

Output:
    pipeline/data/pdfs/{safe_ticker}/{filename}.pdf
    pipeline/data/pdfs/manifest.json (merged)
"""

import json
import re
import sys
import time
from pathlib import Path

import requests

PIPELINE_ROOT = Path(__file__).parent.parent
PDF_DIR = PIPELINE_ROOT / "data" / "pdfs"
MANIFEST_FILE = PDF_DIR / "manifest.json"

NSE_API = "https://www.nse.co.ke/wp-json/wp/v2/media"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Referer": "https://www.nse.co.ke/listed-company-announcements/",
}

# Mapping: ticker -> list of name fragments to match against PDF filenames/titles
# Order matters: more specific strings first
TICKER_NAME_MAP: dict[str, list[str]] = {
    "KCB_NR":   ["kcb-group", "kcb group"],
    "EQTY_NR":  ["equity-group", "equity group"],
    "COOP_NR":  ["co-operative-bank", "co-op-bank", "co op bank", "cooperative bank"],
    "NCBA_NR":  ["ncba-group", "ncba group"],
    "ABSA_NR":  ["absa-bank-kenya", "absa bank kenya"],
    "SBIC_NR":  ["stanbic-holdings", "stanbic holdings"],
    "IMH_NR":   ["im-group", "i-m-group", "im holdings", "i&m group", "i&m holdings"],
    "DTK_NR":   ["diamond-trust", "diamond trust"],
    "SCBK_NR":  ["standard-chartered-bank", "standard chartered bank", "standard chartered kenya"],
    "FMLY_NR":  ["family-bank", "family bank"],
    "HFCK_NR":  ["hf-group", "hf group"],
    "SCOM_NR":  ["safaricom"],
    "EABL_NR":  ["east-african-breweries", "east african breweries"],
    "BAT_NR":   ["british-american-tobacco", "bat-kenya", "bat kenya"],
    "BOC_NR":   ["boc-kenya", "boc kenya"],
    "CARB_NR":  ["carbacid"],
    "UNGA_NR":  ["unga-group", "unga group"],
    "KEGN_NR":  ["kengen"],
    "KPLC_NR":  ["kenya-power", "kplc", "kenya power"],
    "KPC_NR":   ["kenya-pipeline", "kenya pipeline"],
    "TOTL_NR":  ["totalenergies-marketing-kenya", "total energies marketing kenya", "total kenya"],
    "JUB_NR":   ["jubilee-holdings", "jubilee holdings", "jubilee insurance"],
    "KNRE_NR":  ["kenya-reinsurance", "kenya re-insurance", "kenyare"],
    "BRIT_NR":  ["britam-holdings", "britam holdings", "britam"],
    "CIC_NR":   ["cic-insurance", "cic insurance"],
    "LBTY_NR":  ["liberty-kenya", "liberty kenya"],
    "CTUM_NR":  ["centum-investment", "centum"],
    "NSE_NR":   ["nse-plc", "nairobi-securities-exchange", "nse integrated"],
    "NMG_NR":   ["nation-media-group", "nation media group"],
    "KQ_NR":    ["kenya-airways", "kenya airways"],
    "LKL_NR":   ["longhorn"],
    "SCAN_NR":  ["wpp-scangroup", "scangroup"],
    "SGL_NR":   ["standard-group", "standard group"],
    "KUKZ_NR":  ["kakuzi"],
    "SASN_NR":  ["sasini"],
    "CRWN_NR":  ["crown-paints", "crown paints"],
}

# Skip keywords in filename (normalised to lowercase with spaces)
SKIP_KW = [
    "corporate calendar", "forward calendar", "agm notice", "agm proxy", "proxy form",
    "minutes", "polling results", "governance", "sustainability", "esg",
    "remuneration", "training", "strategy", "bbo", "pricelist",
    "cautionary", "rights issue", "offer information", "prospectus",
    "kshs mn other disclosures",  # broker quarterly
]

# Financial result keywords (at least one must be present)
RESULT_KW = [
    "audited", "annual report", "financial result", "financial statement",
    "interim result", "half year", "half-year", "unaudited result",
    "integrated report", "group result",
]


def load_manifest() -> dict:
    if MANIFEST_FILE.exists():
        with open(MANIFEST_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(manifest: dict) -> None:
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def classify_pdf(fname: str, title: str) -> str | None:
    """Return safe_ticker if this PDF belongs to one of our tracked companies, else None."""
    # Normalise: lowercase, replace hyphens/underscores/special chars with spaces
    norm_fname = re.sub(r"[^a-z0-9 ]", " ", fname.lower().replace("%e2%80%93", " ").replace("%e2%80%94", " "))
    norm_title = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    combined = norm_fname + " " + norm_title

    # Must have at least one result keyword
    if not any(kw in combined for kw in RESULT_KW):
        return None

    # Must NOT have skip keywords
    if any(kw in combined for kw in SKIP_KW):
        return None

    # Match to ticker
    for ticker, names in TICKER_NAME_MAP.items():
        if any(name.lower().replace("-", " ") in combined for name in names):
            return ticker

    return None


def fetch_all_pdf_metadata(session: requests.Session) -> list[dict]:
    """Page through the WP media API and return all PDF metadata."""
    results = []
    page = 1
    while True:
        url = (
            f"{NSE_API}?media_type=application&per_page=100"
            f"&page={page}&mime_type=application/pdf"
        )
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                break
            items = resp.json()
            if not items:
                break
            results.extend(items)
            print(f"  [API] Page {page}: {len(items)} items, {len(results)} total")
            if len(items) < 100:
                break
            page += 1
            time.sleep(0.3)
        except Exception as e:
            print(f"  [API] Error on page {page}: {e}")
            break
    return results


def download_pdf(url: str, dest: Path, session: requests.Session) -> bool:
    try:
        resp = session.get(url, timeout=60, stream=True, allow_redirects=True)
        if resp.status_code != 200:
            return False
        ct = resp.headers.get("content-type", "")
        data = b"".join(resp.iter_content(65536))
        if not (data[:4] == b"%PDF" or "pdf" in ct):
            return False
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"      Download error: {e}")
        return False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Download NSE company result PDFs via WP API")
    parser.add_argument("--tickers", nargs="*", help="Specific tickers to download for")
    parser.add_argument("--all", action="store_true", default=True)
    parser.add_argument("--force", action="store_true", help="Re-download existing files")
    args = parser.parse_args()

    target_tickers = set(args.tickers) if args.tickers else set(TICKER_NAME_MAP.keys())

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    session = requests.Session()
    session.headers.update(HEADERS)

    print("Fetching NSE WordPress media API...")
    all_pdfs = fetch_all_pdf_metadata(session)
    print(f"Total items fetched: {len(all_pdfs)}")

    # Classify and collect download tasks
    tasks: dict[str, list[dict]] = {}
    for item in all_pdfs:
        src = item.get("source_url", "")
        if not src or not src.lower().endswith(".pdf"):
            continue
        fname = src.split("/")[-1]
        title = item.get("title", {}).get("rendered", "") if isinstance(item.get("title"), dict) else str(item.get("title", ""))
        ticker = classify_pdf(fname, title)
        if ticker and ticker in target_tickers:
            tasks.setdefault(ticker, []).append({
                "url": src,
                "fname": fname,
                "date": item.get("date", "")[:10],
                "title": title,
            })

    print(f"\nMatched {sum(len(v) for v in tasks.values())} PDFs across {len(tasks)} tickers")

    for ticker, pdfs in sorted(tasks.items()):
        print(f"\n[{ticker}] {len(pdfs)} PDFs")
        ticker_dir = PDF_DIR / ticker
        ticker_dir.mkdir(exist_ok=True)
        tm = manifest.setdefault(ticker, {"name": ticker, "files": {}})

        for pdf in pdfs:
            dest = ticker_dir / pdf["fname"]
            if dest.exists() and not args.force:
                kb = dest.stat().st_size // 1024
                print(f"  [skip] {pdf['fname'][:60]} ({kb}KB)")
                continue
            print(f"  Downloading [{pdf['date']}]: {pdf['fname'][:70]}")
            ok = download_pdf(pdf["url"], dest, session)
            if ok:
                kb = dest.stat().st_size // 1024
                print(f"    Saved {kb}KB")
                tm["files"][pdf["fname"]] = {
                    "url": pdf["url"],
                    "date": pdf["date"],
                    "title": pdf["title"],
                    "size_kb": kb,
                    "extracted": False,
                }
            else:
                print(f"    FAILED")
            time.sleep(0.5)

        save_manifest(manifest)

    print("\n=== Done ===")
    total = sum(len(v.get("files", {})) for v in manifest.values())
    print(f"Total tracked PDFs: {total}")


if __name__ == "__main__":
    main()
