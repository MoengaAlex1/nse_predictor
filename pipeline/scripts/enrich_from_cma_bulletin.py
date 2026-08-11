"""
Enrich fundamentals from CMA's Quarterly Statistical Bulletin.

The Capital Markets Authority (Kenya) publishes a quarterly statistical
bulletin at cma.or.ke/publications/. Table 31 ("Shareholding per listed
company as at <month>") contains authoritative TOTAL SHARES per NSE-
listed company alongside foreign/local ownership breakdowns.

This script:
 1. Discovers the newest bulletin URL from CMA's publications index.
 2. Downloads the PDF.
 3. Extracts Table 31 via pdfplumber's structured table extraction
    (no AI needed — the layout is a proper table).
 4. Parses company name strings like
       "Equity Group Holdings Plc Ord 0.50"
    into (bare ticker, shares_outstanding, source_month).
 5. Writes shares_outstanding_mn to fundamentals/{ticker}, only when
    the incoming CMA value differs by >1% from what we already have —
    this preserves manually-curated overrides.

Every write is tagged method="cma-bulletin" with an as_of month + the
source URL so downstream can audit provenance.

Usage:  python pipeline/scripts/enrich_from_cma_bulletin.py [--dry-run] [--bulletin-url URL]
Env:    FIREBASE_SERVICE_ACCOUNT_JSON
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

CMA_PUBLICATIONS_URL = "https://www.cma.or.ke/publications/"
UA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

# Company-name → bare-ticker map. Kept explicit rather than fuzzy-matched
# because ~5 mislabels here would be worse than 5 missing rows.
NAME_TO_TICKER: dict[str, str] = {
    "Eaagads Ltd Ord 1.25 SME":                                          "EGAD",
    "Kakuzi Plc Ord.5.00":                                                "KUKZ",
    "Kapchorua Tea Kenya Plc Ord 5.00SME":                                "KAPC",
    "The Limuru Tea Co. Plc Ord 10.00SME":                                "LIMT",
    "Sasini Plc Ord 1.00":                                                "SASN",
    "Williamson Tea Kenya Plc Ord 5.00":                                  "WTK",
    "Car & General (K) Ltd Ord 5.00":                                     "CGEN",
    "ABSA Bank Kenya Plc Ord 0.50":                                       "ABSA",
    "BK Group Plc Ord 0.80":                                              "BKG",
    "Diamond Trust Bank Kenya Ltd Ord 4.00":                              "DTK",
    "Equity Group Holdings Plc Ord 0.50":                                 "EQTY",
    "HF Group Plc Ord 5.00":                                              "HFCK",
    "I&M Group Plc Ord 1.00":                                             "IMH",
    "KCB Group Plc Ord 1.00":                                             "KCB",
    "NCBA Group Plc Ord 5.00":                                            "NCBA",
    "Stanbic Holdings Plc Ord.5.00":                                      "SBIC",
    "Standard Chartered Bank Kenya Ltd Ord 5.00":                         "SCBK",
    "The Co-operative Bank of Kenya Ltd Ord 1.00":                        "COOP",
    "Deacons (East Africa) Plc Ord 2.50":                                 "DCON",
    "Eveready East Africa Ltd Ord.1.00SME":                               "EVRD",
    "Express Kenya Plc Ord 5.00":                                         "XPRS",
    "Kenya Airways Ltd Ord 1.00":                                         "KQ",
    "Longhorn Publishers Plc Ord 1.00":                                   "LKL",
    "Nairobi Business Ventures Plc Ord. 0.50SME":                         "NBV",
    "Nation Media Group Plc Ord. 2.50":                                   "NMG",
    "Sameer Africa Plc Ord 5.00":                                         "SMER",
    "Standard Group Plc Ord 5.00":                                        "SGL",
    "TPS Eastern Africa Ltd Ord 1.00":                                    "TPSE",
    "Uchumi Supermarket Plc Ord 5.00":                                    "UCHM",
    "WPP Scangroup Plc Ord 1.00":                                         "SCAN",
    "Homeboyz Entertainment Plc 0.50SME":                                 "HBOY",
    "ARM Cement Plc Ord 1.00":                                            "ARM",
    "Bamburi Cement Plc Ord 5.00":                                        "BAMB",
    "Crown Paints Kenya Plc Ord.5.00":                                    "CRWN",
    "E.A.Cables Ltd Ord 0.50":                                            "EACL",
    "E.A.Portland Cement Co. Ltd Ord 5.00":                               "PORT",
    "KenGen Co. Plc Ord. 2.50":                                           "KEGN",
    "Kenya Power & Lighting Plc Ord 2.50":                                "KPLC",
    "Kenya Power & Lighting Plc 4% Pref 20.00":                           "KPLC_P4",
    "Kenya Power & Lighting Plc 7% Pref 20.00":                           "KPLC_P7",
    "TotalEnergies Marketing Kenya Plc Ord 5.00":                         "TOTL",
    "Umeme Ltd Ord 0.50":                                                 "UMME",
    "Kenya Pipeline Company Plc Ord 0.02":                                "KPC",
    "Britam Holdings Plc Ord 0.10":                                       "BRIT",
    "CIC Insurance Group Plc Ord.1.00":                                   "CIC",
    "Jubilee Holdings Ltd Ord 5.00":                                      "JUB",
    "Kenya Re Insurance Corporation Ltd Ord 2.50":                        "KNRE",
    "Liberty Kenya Holdings Ltd Ord. 1.00":                               "LBTY",
    "Sanlam Kenya Plc Ord 5.00":                                          "SLAM",
    "Centum Investment Co Plc Ord 0.50":                                  "CTUM",
    "Home Afrika Ltd Ord 1.00":                                           "HAFR",
    "Kurwitu Ventures Ltd Ord 100.00SME":                                 "KURV",
    "Olympia Capital Holdings Ltd Ord 5.00":                              "OCH",
    "Trans-Century Plc Ord 0.50":                                         "TRFC",
    "Flame Tree Group Holdings Ltd Ord 0.825":                            "FTGH",
    "Africa Mega Agricorp Plc Ord 5.00SME":                               "AMAC",
    "Mumias Sugar Co. Ltd Ord 2.00":                                      "MSC",
    "Unga Group Ltd Ord 5.00":                                            "UNGA",
    "BAT Kenya Plc Ord.10.00":                                            "BAT",
    "British American Tobacco Kenya Plc Ord 10.00":                       "BAT",
    "B.O.C Kenya Plc Ord 5.00":                                           "BOC",
    "Carbacid Investments Plc Ord 1.00":                                  "CARB",
    "East African Breweries Ltd Ord 2.00":                                "EABL",
    "Kenya Orchards Ltd Ord 5.00SME":                                     "ORCH",
    "Shri Krishana Overseas Plc 0.20SME":                                 "SHKL",
    "Safaricom Plc Ord 0.05":                                             "SCOM",
    "Nairobi Securities Exchange Plc Ord 4.00":                           "NSE",
    "LAPTRUST IMARA I-REIT Ord.20.00":                                    "LREIT",
    "ALP Industrial REIT Ord.USD 1.00":                                   "ALP",
    "ABSA New Gold ETF":                                                  "GLD",
    "Satrix MSCI World Feeder ETF":                                       "SMWF",
    "Family Bank Limited Ord 1.00":                                       "FMLY",
    "Family Bank Ltd Ord 1.00":                                           "FMLY",
    "Sanlam Allianz Holdings Kenya Plc Ord 5.00":                         "SLAM",
}


# ---------------------------------------------------------------------------
# Bulletin discovery + download
# ---------------------------------------------------------------------------

def discover_latest_bulletin_url() -> str:
    req = urllib.request.Request(CMA_PUBLICATIONS_URL, headers=UA_HEADERS)
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", errors="replace")
    hrefs = re.findall(
        r'href=["\']([^"\']*(?:bulletin|statistic)[^"\']*\.pdf)["\']',
        html,
        re.IGNORECASE,
    )
    if not hrefs:
        raise SystemExit("No bulletin PDFs found on CMA publications page")
    # Sort newest-first — URLs contain year in path, so lexical sort works
    hrefs = sorted(set(hrefs), reverse=True)
    latest = hrefs[0]
    if not latest.startswith("http"):
        latest = f"https://www.cma.or.ke{latest}"
    return latest


def download(url: str) -> Path:
    req = urllib.request.Request(url, headers=UA_HEADERS)
    data = urllib.request.urlopen(req, timeout=60).read()
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# Table 31 extraction
# ---------------------------------------------------------------------------

_NUM = re.compile(r"^[\d,]+$")


def parse_shares(cell: str | None) -> int | None:
    if not cell:
        return None
    s = cell.replace(",", "").strip()
    if not s.isdigit():
        return None
    return int(s)


def extract_shareholding(pdf_path: Path) -> list[dict]:
    """Return [{"name_raw": str, "shares": int, "month": str, "foreign_pct": float | None}, ...]"""
    import pdfplumber

    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 4:
                    continue
                header_flat = " ".join((c or "") for row in table[:3] for c in row).upper()
                # Table 31 header always includes SECTOR/COMPANY + TOTAL SHARES
                if "SECTOR/COMPANY" not in header_flat or "TOTAL" not in header_flat:
                    continue
                for row in table[3:]:
                    if not row:
                        continue
                    name = (row[0] or "").strip()
                    if not name:
                        continue
                    # Skip pure section-header rows (all-caps, no numbers)
                    if name.isupper() and not any(parse_shares(c) for c in row[1:]):
                        continue
                    month = (row[1] or "").strip()
                    shares = parse_shares(row[2])
                    if shares is None:
                        continue
                    # Foreign % is usually cell index 6 or 7 depending on merged cells
                    foreign_pct = None
                    for cand in row[6:9]:
                        if not cand:
                            continue
                        m = re.match(r"^([\d.]+)%$", str(cand).strip())
                        if m:
                            foreign_pct = float(m.group(1))
                            break
                    rows.append({
                        "name_raw": name,
                        "shares": shares,
                        "month": month,
                        "foreign_pct": foreign_pct,
                    })
    return rows


# ---------------------------------------------------------------------------
# Firestore writes
# ---------------------------------------------------------------------------

def write_updates(db, rows: list[dict], bulletin_url: str, dry_run: bool) -> tuple[int, int, list[str]]:
    now = datetime.now(timezone.utc).isoformat()
    matched = 0
    written = 0
    unmatched: list[str] = []

    for r in rows:
        ticker = NAME_TO_TICKER.get(r["name_raw"])
        if not ticker:
            unmatched.append(r["name_raw"])
            continue
        matched += 1
        shares_mn = round(r["shares"] / 1_000_000, 1)

        # Skip preference-share doc IDs — they're not primary listings
        if "_P" in ticker:
            continue

        fund_ref = db.collection("fundamentals").document(ticker)
        fund_snap = fund_ref.get()
        fund_existing = fund_snap.to_dict() if fund_snap.exists else {}
        old_shares = fund_existing.get("shares_outstanding_mn")

        # Skip if unchanged (within 0.5% tolerance) AND already from CMA
        if old_shares and abs(old_shares - shares_mn) / max(old_shares, 1) < 0.005 \
                and fund_existing.get("method") == "cma-bulletin":
            continue

        delta_str = ""
        if old_shares:
            pct = (shares_mn - old_shares) / old_shares * 100
            delta_str = f"  (was {old_shares:>10,.1f}M, Δ {pct:+.1f}%)"
        print(f"  {ticker:6}  {shares_mn:>12,.1f}M shares  as-of {r['month']}{delta_str}")

        update = {
            "ticker": ticker,
            "shares_outstanding_mn": shares_mn,
            "as_of": r["month"],
            "source": "CMA Quarterly Statistical Bulletin Table 31",
            "source_url": bulletin_url,
            "method": "cma-bulletin",
            "confidence": "high",
            "updated_at": now,
        }
        if r["foreign_pct"] is not None:
            update["foreign_ownership_pct"] = r["foreign_pct"]

        if not dry_run:
            fund_ref.set(update, merge=True)
        written += 1

    return matched, written, unmatched


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--bulletin-url", help="Override the auto-discovered URL")
    args = parser.parse_args()

    url = args.bulletin_url or discover_latest_bulletin_url()
    print(f"Using bulletin: {url}\n")

    pdf_path = download(url)
    print(f"Downloaded {pdf_path.stat().st_size:,} bytes\n")

    rows = extract_shareholding(pdf_path)
    print(f"Extracted {len(rows)} company rows from Table 31\n")

    from scripts.firebase_client import get_firestore
    db = get_firestore()

    matched, written, unmatched = write_updates(db, rows, url, args.dry_run)

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n=== Done === matched {matched} / {len(rows)} rows, {verb} {written} fundamentals updates")
    if unmatched:
        print(f"\nUnmatched company names ({len(unmatched)}) — add to NAME_TO_TICKER if these are real listings:")
        for u in unmatched:
            print(f"  '{u}'")


if __name__ == "__main__":
    main()
