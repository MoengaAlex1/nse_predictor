"""
Scrape NSE Daily Market Bulletin PDFs for corporate actions.

NSE publishes a daily equity trading bulletin at
    https://www.nse.co.ke/wp-content/uploads/{DD}-{MON}-{YY}.pdf
Each bulletin includes a CORPORATE ACTIONS block listing every open
dividend announcement in a highly regular one-line-per-row format:

    Safaricom Plc Ord 0.05; KE1000001402; announced a Final Dividend
    of Kes.1.15 on 07-May-2026; Books Closure: 04-Aug-2026;
    Payment date:04-Sep-2026

The same row typically appears daily from the announcement date until
the payment date (1-3 months), so we dedupe by the natural key
(ISIN, announcement_date, amount_kes, type).

Pipeline
--------
1. Iterate every trading day between --start and --end.
2. Download each PDF (skip if 404 — non-trading day).
3. Render each page to an image, OCR via pytesseract.
4. Regex-extract corporate action lines.
5. Map ISIN → bare ticker via companies.isin lookup (loaded once from
   Firestore). Fall back to matching the company name string.
6. Dedupe against records already written this run + Firestore's
   existing dividends[] array (URL is per-day but our key excludes URL).
7. Write to financials/{ticker}.dividends[] with source="nse-daily-bulletin".

Usage:
    python pipeline/scripts/scrape_nse_daily_bulletins.py \\
        --start 2020-01-01 --end 2026-08-11 [--dry-run] [--limit 30]

Env: FIREBASE_SERVICE_ACCOUNT_JSON
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

UA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

# Corporate action line regex. Tolerates lots of OCR quirks:
# extra whitespace, missing colons, Kes vs KES, "Book" vs "Books", etc.
CORP_ACTION_RE = re.compile(
    r"(?P<name>[A-Za-z][\w\s.,&()\-']+?)\s*(?:Ord|Ord\.|Ord[a-z]*)\s*\d[\d.]*[A-Z]*\s*;\s*"
    r"(?P<isin>KE\d{10,12}|)\s*;\s*"
    r"announced\s+a\s+(?P<type>Final|Interim|Special|First\s*&\s*Final|First\s*and\s*Final|Total|Scrip|Bonus|Preference)\s+(?:and\s+\w+\s+)?Dividend\s+of\s+"
    r"Kes\.?\s*(?P<amount>\d+(?:\.\d+)?)\s+"
    r"on\s+(?P<ann_date>\d{1,2}-[A-Za-z]{3}-\d{2,4})\s*[;.,]?\s*"
    r"Books?\s+Closure\s*:?\s*(?P<ex_date>\d{1,2}-[A-Za-z]{3}-\d{2,4}|SUBJECT\s+TO\s+APPROVAL|-|N/A)?\s*[;.,]?\s*"
    r"Payment\s+date\s*:?\s*(?P<pay_date>\d{1,2}-[A-Za-z]{3}-\d{2,4}|SUBJECT\s+TO\s+APPROVAL|-|N/A)?",
    re.IGNORECASE,
)

_MONTH_MAP = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


def parse_iso_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.upper() in {"SUBJECT TO APPROVAL", "-", "N/A", ""}:
        return None
    m = re.match(r"(\d{1,2})-([A-Za-z]{3})-(\d{2,4})", raw)
    if not m:
        return None
    day, mon, year = int(m.group(1)), m.group(2).title(), m.group(3)
    if mon not in _MONTH_MAP:
        return None
    year = int(year) if len(year) == 4 else (2000 + int(year))
    try:
        return date(year, _MONTH_MAP[mon], day).isoformat()
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Bulletin URL + download
# ---------------------------------------------------------------------------

def bulletin_url(d: date) -> str:
    mon = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"][d.month - 1]
    return f"https://www.nse.co.ke/wp-content/uploads/{d.day:02d}-{mon}-{d.year % 100:02d}.pdf"


def download(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=UA_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status != 200:
                return None
            return r.read()
    except urllib.request.HTTPError:
        return None
    except Exception as exc:
        print(f"    ! download error: {exc}")
        return None


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def ocr_bulletin(pdf_bytes: bytes) -> str:
    """Return combined OCR text for the whole PDF. Handles image-only PDFs
    that pdfplumber can't read directly."""
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image
    import io

    text_parts = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            # Try native text first — some bulletins have selectable text
            native = page.get_text().strip()
            if native and len(native) > 200:
                text_parts.append(native)
                continue
            # Fall back to OCR
            pix = page.get_pixmap(dpi=250)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            ocr_text = pytesseract.image_to_string(img)
            text_parts.append(ocr_text)
    return "\n".join(text_parts)


# ---------------------------------------------------------------------------
# Corporate action extraction
# ---------------------------------------------------------------------------

def extract_actions(text: str) -> list[dict]:
    # First isolate the CORPORATE ACTIONS block if present — reduces false
    # positives from the market-summary section.
    lower = text.lower()
    idx = lower.find("corporate action")
    block = text[idx:] if idx >= 0 else text
    # Cut off before next section header if any (LIABILITIES, TRANSACTION, etc.)
    for stopper in ["LIABILITIES", "TRANSACTIONS SUMMARY", "MARKET STATISTICS", "END OF DAY"]:
        j = block.upper().find(stopper)
        if j > 0:
            block = block[:j]

    out = []
    for m in CORP_ACTION_RE.finditer(block):
        d = m.groupdict()
        rec = {
            "name":              d["name"].strip(),
            "isin":              (d.get("isin") or "").strip() or None,
            "type":              d["type"].strip().lower().replace(" ", "-"),
            "amount_kes":        float(d["amount"]),
            "announcement_date": parse_iso_date(d["ann_date"]),
            "ex_date":           parse_iso_date(d.get("ex_date")),
            "payment_date":      parse_iso_date(d.get("pay_date")),
        }
        # Sanity: annual dividend of >200 KES is suspicious (OCR misreads)
        if rec["amount_kes"] > 200:
            continue
        # Normalise "first-&-final" / "first-and-final" → "final"
        if "first" in rec["type"] and "final" in rec["type"]:
            rec["type"] = "final"
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# ISIN → ticker map (loaded from Firestore + fallback hardcoded)
# ---------------------------------------------------------------------------

def load_isin_map(db) -> dict[str, str]:
    """Try to load ISIN→ticker map from companies collection. Fall back to
    a hand-tuned map covering the majors."""
    m = {}
    try:
        for doc in db.collection("companies").stream():
            data = doc.to_dict() or {}
            isin = data.get("isin")
            if isin:
                m[isin.strip().upper()] = doc.id
    except Exception:
        pass
    # Merge in hand-tuned fallback for tickers whose companies doc lacks isin
    fallback = {
        "KE1000001402": "SCOM",  "KE0000000141": "CRWN",  "KE2000002168": "LBTY",
        "KE0000000604": "KNRE",  "KE3000009674": "NSE",   "KE0000000463": "TOTL",
        "KE0000000273": "JUB",   "KE0000000042": "BOC",   "KE0000000109": "CGEN",
        "KE0000000554": "EQTY",  "KE0000000158": "DTK",   "KE0000000190": "PORT",
    }
    for k, v in fallback.items():
        m.setdefault(k, v)
    return m


NAME_HINTS: list[tuple[str, str]] = [
    # substr, ticker (checked lowercase, in order of specificity)
    ("safaricom", "SCOM"), ("equity group", "EQTY"), ("kcb group", "KCB"),
    ("co-operative", "COOP"), ("east african breweries", "EABL"),
    ("british american tobacco", "BAT"), ("bat kenya", "BAT"),
    ("absa bank kenya", "ABSA"), ("ncba group", "NCBA"),
    ("stanbic holdings", "SBIC"), ("i&m group", "IMH"), ("i & m group", "IMH"),
    ("diamond trust", "DTK"), ("standard chartered", "SCBK"),
    ("kengen", "KEGN"), ("kenya power", "KPLC"), ("kenya pipeline", "KPC"),
    ("totalenergies", "TOTL"), ("total kenya", "TOTL"),
    ("jubilee holdings", "JUB"), ("britam holdings", "BRIT"),
    ("cic insurance", "CIC"), ("kenya re", "KNRE"), ("liberty kenya", "LBTY"),
    ("centum", "CTUM"), ("nairobi securities exchange", "NSE"), ("nse plc", "NSE"),
    ("nation media", "NMG"), ("kenya airways", "KQ"), ("longhorn", "LKL"),
    ("wpp scangroup", "SCAN"), ("scangroup", "SCAN"), ("standard group", "SGL"),
    ("kakuzi", "KUKZ"), ("sasini", "SASN"), ("crown paints", "CRWN"),
    ("car & general", "CGEN"), ("car and general", "CGEN"), ("bk group", "BKG"),
    ("carbacid", "CARB"), ("eaagads", "EGAD"), ("nairobi business", "NBV"),
    ("olympia", "OCH"), ("unga", "UNGA"), ("flame tree", "FTGH"),
    ("home afrika", "HAFR"), ("shri", "SHKL"), ("sanlam", "SLAM"),
    ("eveready", "EVRD"), ("kapchorua", "KAPC"), ("kurwitu", "KURV"),
    ("limuru", "LIMT"), ("sameer", "SMER"), ("trans-century", "TRFC"),
    ("transcentury", "TRFC"), ("uchumi", "UCHM"), ("umeme", "UMME"),
    ("williamson", "WTK"), ("alp", "ALP"), ("family bank", "FMLY"),
    ("hf group", "HFCK"), ("housing finance", "HFCK"), ("bamburi", "BAMB"),
    ("mumias", "MSC"), ("tps", "TPSE"), ("centum", "CTUM"),
    ("nairobi business ventures", "NBV"), ("olympia capital", "OCH"),
    ("boc kenya", "BOC"), ("british american tobacco kenya", "BAT"),
]


def match_ticker(rec: dict, isin_map: dict[str, str]) -> str | None:
    if rec.get("isin"):
        t = isin_map.get(rec["isin"])
        if t:
            return t
    name_lc = rec["name"].lower()
    for pattern, tkr in NAME_HINTS:
        if pattern in name_lc:
            return tkr
    return None


# ---------------------------------------------------------------------------
# Firestore merge
# ---------------------------------------------------------------------------

def merge_dividends(db, ticker: str, incoming: list[dict], bulletin_date: str, url: str, dry_run: bool) -> int:
    """Add each new dividend record. Dedup by (announcement_date, amount, type)."""
    doc_ref = db.collection("financials").document(ticker)
    snap = doc_ref.get()
    existing = snap.to_dict() if snap.exists else {}
    existing_divs = existing.get("dividends", []) or []

    def key(r):
        return (
            r.get("announcement_date") or "",
            round(float(r.get("amount_kes") or 0), 2),
            (r.get("type") or "").lower(),
        )

    existing_keys = {key(r) for r in existing_divs if isinstance(r, dict)}
    fresh: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()
    for r in incoming:
        if key(r) in existing_keys:
            continue
        existing_keys.add(key(r))
        fresh.append({
            "announcement_date": r["announcement_date"],
            "ex_date":           r["ex_date"],
            "payment_date":      r["payment_date"],
            "amount_kes":        r["amount_kes"],
            "type":              r["type"],
            "isin":              r.get("isin"),
            "source":            "nse-daily-bulletin",
            "source_url":        url,
            "first_seen_bulletin": bulletin_date,
            "extracted_at":      now,
        })

    if fresh and not dry_run:
        merged = sorted(existing_divs + fresh, key=lambda r: r.get("announcement_date", "") or "", reverse=True)
        doc_ref.set({"dividends": merged}, merge=True)

    return len(fresh)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def daterange(start: date, end: date):
    d = start
    while d <= end:
        # Skip weekends — NSE doesn't trade
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, default="2020-01-01")
    parser.add_argument("--end", type=str, default=None, help="default: today")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="cap on bulletins to process")
    args = parser.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()

    from scripts.firebase_client import get_firestore
    db = get_firestore()
    isin_map = load_isin_map(db)
    print(f"ISIN→ticker map: {len(isin_map)} entries\n")

    days = list(daterange(start, end))
    if args.limit:
        days = days[-args.limit:]  # most recent N (most recent bulletins first)
    print(f"Processing {len(days)} weekdays from {days[0]} to {days[-1]}\n")

    total_found = 0
    total_records = 0
    total_new = 0
    dividends_per_ticker: dict[str, int] = {}
    misses = 0

    for i, d in enumerate(days):
        url = bulletin_url(d)
        pdf = download(url)
        if not pdf:
            misses += 1
            continue
        total_found += 1
        try:
            text = ocr_bulletin(pdf)
        except Exception as exc:
            print(f"  {d} OCR failed: {exc}")
            continue
        records = extract_actions(text)
        if not records:
            continue
        total_records += len(records)

        # Group by ticker so we do one Firestore write per ticker per day
        by_ticker: dict[str, list[dict]] = {}
        for r in records:
            t = match_ticker(r, isin_map)
            if not t:
                continue
            by_ticker.setdefault(t, []).append(r)

        for tkr, recs in by_ticker.items():
            n = merge_dividends(db, tkr, recs, d.isoformat(), url, args.dry_run)
            if n:
                dividends_per_ticker[tkr] = dividends_per_ticker.get(tkr, 0) + n
                total_new += n

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(days)}] {d}: {total_found} bulletins found, {total_new} new dividends")

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n=== Done ===")
    print(f"  Bulletins fetched: {total_found} / {len(days)} weekdays  ({misses} 404s)")
    print(f"  Corporate actions parsed: {total_records}")
    print(f"  Deduped {verb}: {total_new} new dividend records across {len(dividends_per_ticker)} tickers")
    if dividends_per_ticker:
        print(f"\n  Top tickers by new records:")
        for tkr, n in sorted(dividends_per_ticker.items(), key=lambda kv: -kv[1])[:15]:
            print(f"    {tkr:6}  +{n}")


if __name__ == "__main__":
    main()
