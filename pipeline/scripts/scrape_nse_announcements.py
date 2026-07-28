"""
Scrape NSE WordPress media API for company announcements and corporate actions.
Classifies PDFs and seeds Firestore announcements/corporate_actions/dividends arrays.

Each record stored: {"date": "YYYY-MM-DD", "type": "...", "title": "...", "url": "..."}

Usage:
    python pipeline/scripts/scrape_nse_announcements.py [--dry-run] [--tickers SCOM_NR ...]
    # Refresh token first:
    # firebase projects:list && python pipeline/scripts/scrape_nse_announcements.py
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))

PROJECT_ID = "nse-market-dashboard"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    "/databases/(default)/documents"
)

NSE_MEDIA_API = "https://www.nse.co.ke/wp-json/wp/v2/media"
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nse.co.ke/listed-company-announcements/",
}

TICKER_NAME_MAP: dict[str, list[str]] = {
    "KCB_NR":   ["kcb group", "kcb bank", "kcb-group"],
    "EQTY_NR":  ["equity group", "equity bank", "equity-group"],
    "COOP_NR":  ["co-operative bank", "co-op bank", "cooperative bank", "co operative bank"],
    "NCBA_NR":  ["ncba group", "ncba bank", "ncba-group"],
    "ABSA_NR":  ["absa bank kenya", "absa bank ke", "absa-bank-kenya"],
    "SBIC_NR":  ["stanbic holdings", "stanbic bank", "stanbic-holdings"],
    "IMH_NR":   ["i m group", "i&m group", "i&m holdings", "im holdings", "im-group"],
    "DTK_NR":   ["diamond trust bank", "diamond trust bank kenya", "dtb kenya"],
    "SCBK_NR":  ["standard chartered bank kenya", "standard chartered kenya", "standard chartered bank ke"],
    "FMLY_NR":  ["family bank"],
    "HFCK_NR":  ["hf group", "hf-group", "housing finance"],
    "SCOM_NR":  ["safaricom"],
    "EABL_NR":  ["east african breweries", "eabl"],
    "BAT_NR":   ["british american tobacco", "bat kenya"],
    "BOC_NR":   ["boc kenya"],
    "CARB_NR":  ["carbacid"],
    "UNGA_NR":  ["unga group"],
    "KEGN_NR":  ["kengen"],
    "KPLC_NR":  ["kenya power", "kplc"],
    "KPC_NR":   ["kenya pipeline"],
    "TOTL_NR":  ["totalenergies marketing kenya", "total energies marketing kenya", "total kenya", "totalenergies marketing"],
    "JUB_NR":   ["jubilee holdings", "jubilee insurance"],
    "KNRE_NR":  ["kenya reinsurance", "kenya re insurance", "kenya re-insurance", "kenya re"],
    "BRIT_NR":  ["britam holdings", "britam"],
    "CIC_NR":   ["cic insurance", "cic group"],
    "LBTY_NR":  ["liberty kenya"],
    "CTUM_NR":  ["centum investment", "centum"],
    "NSE_NR":   ["nse plc", "nairobi securities exchange", "nse-plc"],
    "NMG_NR":   ["nation media group"],
    "KQ_NR":    ["kenya airways"],
    "LKL_NR":   ["longhorn"],
    "SCAN_NR":  ["wpp scangroup", "scangroup"],
    "SGL_NR":   ["standard group"],
    "KUKZ_NR":  ["kakuzi"],
    "SASN_NR":  ["sasini"],
    "CRWN_NR":  ["crown paints"],
}

# Ordered from most specific to least to avoid misclassification
DIVIDEND_KW = [
    "dividend notice", "dividend payment", "interim dividend", "final dividend",
    "proposed dividend", "dividend declaration",
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
    "kshs mn other disclosures",  # broker aggregate quarterly reports, not company filings
    "prospectus", "pre-listing",
    "erp system",
]


# ---------------------------------------------------------------------------
# Firestore REST helpers
# ---------------------------------------------------------------------------

def _to_firestore(value: Any) -> dict:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_to_firestore(v) for v in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {k: _to_firestore(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


def _from_firestore(fv: dict) -> Any:
    if "nullValue" in fv:
        return None
    if "booleanValue" in fv:
        return fv["booleanValue"]
    if "integerValue" in fv:
        return int(fv["integerValue"])
    if "doubleValue" in fv:
        return fv["doubleValue"]
    if "stringValue" in fv:
        return fv["stringValue"]
    if "arrayValue" in fv:
        return [_from_firestore(v) for v in fv.get("arrayValue", {}).get("values", [])]
    if "mapValue" in fv:
        return {k: _from_firestore(v) for k, v in fv.get("mapValue", {}).get("fields", {}).items()}
    return None


def get_access_token() -> str:
    config = Path.home() / ".config" / "configstore" / "firebase-tools.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    token = data["tokens"]["access_token"]
    if not token:
        raise RuntimeError("No access_token. Run: firebase login && firebase projects:list")
    return token


def firestore_get(token: str, ticker: str) -> dict:
    url = f"{FIRESTORE_BASE}/financials/{ticker}"
    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    fields = resp.json().get("fields", {})
    return {k: _from_firestore(v) for k, v in fields.items()}


def firestore_patch_fields(token: str, ticker: str, updates: dict[str, Any]) -> None:
    mask = "&".join(f"updateMask.fieldPaths={k}" for k in updates)
    url = f"{FIRESTORE_BASE}/financials/{ticker}?{mask}"
    resp = requests.patch(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"fields": {k: _to_firestore(v) for k, v in updates.items()}},
        timeout=30,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

def _norm(fname: str, title: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (fname + " " + (title or "")).lower())


def classify_pdf(fname: str, title: str) -> str | None:
    """Return 'financial_result', 'dividend', 'agm', 'corporate_action', or None."""
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


def match_ticker(fname: str, title: str) -> str | None:
    norm = _norm(fname, title)
    for ticker, names in TICKER_NAME_MAP.items():
        if any(name in norm for name in names):
            return ticker
    return None


# ---------------------------------------------------------------------------
# WordPress media fetch
# ---------------------------------------------------------------------------

def fetch_all_media(session: requests.Session) -> list[dict]:
    results = []
    page = 1
    while True:
        url = (
            f"{NSE_MEDIA_API}?media_type=application&per_page=100"
            f"&page={page}&mime_type=application/pdf&orderby=date&order=desc"
        )
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200:
                break
            items = resp.json()
            if not items:
                break
            results.extend(items)
            print(f"  [API] page {page}: {len(items)} items, {len(results)} total")
            if len(items) < 100:
                break
            page += 1
            time.sleep(0.3)
        except Exception as exc:
            print(f"  [API] Error page {page}: {exc}")
            break
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Scrape NSE announcements → Firestore")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tickers", nargs="*")
    args = parser.parse_args()

    target_tickers = set(args.tickers) if args.tickers else set(TICKER_NAME_MAP.keys())

    session = requests.Session()
    session.headers.update(HTTP_HEADERS)

    print("Fetching all PDFs from NSE WordPress media API...")
    all_pdfs = fetch_all_media(session)
    print(f"Total PDFs fetched: {len(all_pdfs)}\n")

    # Classify and group by ticker
    # ticker → {doc_type: [records]}
    classified: dict[str, dict[str, list[dict]]] = {}
    skipped_kw = 0
    unmatched_ticker = 0
    unclassified = 0

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
            skipped_kw += 1
            continue

        ticker = match_ticker(fname, title)
        if not ticker:
            unclassified += 1
            continue
        if ticker not in target_tickers:
            continue

        record: dict[str, str] = {
            "date": item.get("date", "")[:10],
            "type": doc_type,
            "title": title,
            "url": src,
        }
        tc = classified.setdefault(ticker, {})
        tc.setdefault(doc_type, []).append(record)

    total_matched = sum(
        sum(len(v) for v in tc.values()) for tc in classified.values()
    )
    print(f"Matched:     {total_matched} PDFs across {len(classified)} tickers")
    print(f"Skipped:     {skipped_kw} (matched a skip keyword)")
    print(f"Unclassified:{unclassified} (no ticker match)")

    if not args.dry_run:
        token = get_access_token()
        print(f"\nUsing Firebase CLI access token ({token[:20]}...)")

    updated = 0
    errors: list[tuple[str, str]] = []

    for ticker in sorted(classified):
        tc = classified[ticker]
        type_summary = ", ".join(f"{dt}×{len(recs)}" for dt, recs in sorted(tc.items()))
        print(f"\n[{ticker}] {type_summary}")
        for dt, recs in sorted(tc.items()):
            for r in sorted(recs, key=lambda x: x["date"], reverse=True)[:2]:
                print(f"  [{r['date']}] {r['type']:20} {r['title'][:55]}")

        if args.dry_run:
            continue

        # Read existing doc from Firestore
        try:
            existing = firestore_get(token, ticker)
        except requests.HTTPError as exc:
            print(f"  -> GET error: {exc}")
            errors.append((ticker, f"GET {exc}"))
            continue

        existing_corp = existing.get("corporate_actions", [])
        existing_divs = existing.get("dividends", [])
        existing_ann = existing.get("announcements", [])

        corp_urls = {r.get("url") for r in existing_corp}
        div_urls = {r.get("url") for r in existing_divs}
        ann_urls = {r.get("url") for r in existing_ann}

        new_corp = [
            r for r in tc.get("corporate_action", []) + tc.get("agm", [])
            if r["url"] not in corp_urls
        ]
        new_divs = [r for r in tc.get("dividend", []) if r["url"] not in div_urls]
        new_ann = [
            r for r in tc.get("financial_result", []) if r["url"] not in ann_urls
        ]

        if not (new_corp or new_divs or new_ann):
            print("  -> no new records")
            continue

        updates: dict[str, list] = {}
        if new_corp:
            merged = sorted(
                existing_corp + new_corp, key=lambda r: r.get("date", ""), reverse=True
            )
            updates["corporate_actions"] = merged
            print(f"  -> +{len(new_corp)} corporate_actions (total {len(merged)})")
        if new_divs:
            merged = sorted(
                existing_divs + new_divs, key=lambda r: r.get("date", ""), reverse=True
            )
            updates["dividends"] = merged
            print(f"  -> +{len(new_divs)} dividends (total {len(merged)})")
        if new_ann:
            merged = sorted(
                existing_ann + new_ann, key=lambda r: r.get("date", ""), reverse=True
            )
            updates["announcements"] = merged
            print(f"  -> +{len(new_ann)} announcements (total {len(merged)})")

        try:
            firestore_patch_fields(token, ticker, updates)
            updated += 1
        except requests.HTTPError as exc:
            print(f"  -> PATCH error: {exc}")
            errors.append((ticker, f"PATCH {exc}"))

        time.sleep(0.2)

    if args.dry_run:
        print(f"\n[DRY RUN] Would update {len(classified)} tickers")
    else:
        print(f"\n=== Done === Updated {updated}/{len(classified)} tickers")
        if errors:
            print("Errors:")
            for t, e in errors:
                print(f"  {t}: {e}")


if __name__ == "__main__":
    main()
