"""
Scrapes the official NSE daily market report PDF and writes all company
OHLCV records to Firebase RTDB.

The NSE daily report PDFs are scanned images (no selectable text), so this
script uses pdfplumber + pytesseract OCR to extract price rows.

Column order in OCR output:
  52WK_HIGH  52WK_LOW  <company name + ISIN + code + status>
  DAY_HIGH  DAY_LOW  DAY_CLOSE  PREV_CLOSE  VOLUME

Usage:
  python pipeline/scripts/scrape_nse_pdf.py [--date 2026-07-24] [--dry-run]
  python pipeline/scripts/scrape_nse_pdf.py --pdf 21-JUL-26.pdf --dry-run
"""
import argparse
import datetime
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

import pdfplumber
import pytesseract
import requests

# Ensure repo root is on sys.path for sibling-package imports (firebase_client, firebase_rtdb)
_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Tesseract binary path for Windows
_TESSERACT_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_TESSERACT_WIN):
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WIN

# ---------------------------------------------------------------------------
# Column indices — used only in parse_price_row() for text-mode PDFs (fallback)
# ---------------------------------------------------------------------------
COL_PREV_CLOSE = 0
COL_OPEN       = 1
COL_HIGH       = 2
COL_LOW        = 3
COL_CLOSE      = 4
COL_CHANGE     = 5
COL_PCT_CHANGE = 6
COL_VOLUME     = 7
COL_VALUE      = 8

# ---------------------------------------------------------------------------
# Company name → ticker mapping (used for table-mode PDFs; OCR uses NSE_PHRASES)
# ---------------------------------------------------------------------------
COMPANY_TO_TICKER: dict[str, str] = {
    "SAFARICOM":          "SCOM",
    "KCB GROUP":          "KCB",
    "KCB":                "KCB",
    "EQUITY GROUP":       "EQTY",
    "EQUITY":             "EQTY",
    "CO-OPERATIVE":       "COOP",
    "COOP BANK":          "COOP",
    "EAST AFRICAN BREW":  "EABL",
    "EABL":               "EABL",
    "BAMBURI":            "BAMB",
    "KENGEN":             "KEGN",
    "KENYA POWER":        "KPLC",
    "NATION MEDIA":       "NMG",
    "BRITAM":             "BRIT",
    "JUBILEE":            "JUB",
    "CIC INSURANCE":      "CIC",
    "LIBERTY":            "LBTY",
    "SANLAM":             "SLAM",
    "STANCHART":          "SCBK",
    "STANDARD CHART":     "SCBK",
    "NCBA":               "NCBA",
    "ABSA":               "ABSA",
    "DIAMOND TRUST":      "DTK",
    "DTB":                "DTK",
    "I&M":                "IMH",
    "HF GROUP":           "HFCK",
    "HOUSING FINANCE":    "HFCK",
    "CENTUM":             "CTUM",
    "TRANSCENTURY":       "TCL",
    "TOTAL ENERGIES":     "TOTL",
    "TOTAL":              "TOTL",
    "CARBACID":           "CARB",
    "CROWN PAINT":        "BERG",
    "BERGER":             "BERG",
    "UNGA":               "UNGA",
    "KAKUZI":             "KUKZ",
    "LIMURU TEA":         "LIMT",
    "WILLIAMSON":         "WLMB",
    "ATHI RIVER":         "ARM",
    "ARM CEMENT":         "ARM",
    "EAST AFRICAN CABLES":"CABL",
    "MARSHALLS":          "MASH",
    "LONGHORN":           "LKL",
    "KENYA AIRWAYS":      "KQ",
    "UCHUMI":             "UCHM",
    "TPS EASTERN":        "TPSE",
    "BAT KENYA":          "BAT",
    "BAT":                "BAT",
    "MUMIAS":             "MSC",
    "EXPRESS":            "XPRS",
    "KENYA RE":           "KERE",
    "STANDARD MEDIA":     "SGL",
    "ICDC":               "ICDC",
}

# ---------------------------------------------------------------------------
# OCR phrase → ticker (comprehensive, ordered longest-first for greedy match)
# ---------------------------------------------------------------------------
NSE_PHRASES: dict[str, str] = {
    # Agricultural
    "enagad":                        "EGAD",
    "eangads":                       "EGAD",   # OCR variant
    "eacgads":                       "EGAD",   # OCR variant
    "eagads":                        "EGAD",   # OCR variant
    "kakuzi":                        "KUKZ",
    "kapchorua tea":                 "KAPC",
    "kopackhora tea":                "KAPC",
    "limuru tea":                    "LIMT",
    "sasini":                        "SASN",
    "sesini":                        "SASN",   # OCR variant
    "williamson tea":                "WTK",
    # Automobiles
    "car and general":               "CGEN",
    "car & general":                 "CGEN",   # OCR variant
    "car&general":                   "CGEN",   # OCR variant
    # Banking
    "absa bank":                     "ABSA",
    "bk group":                      "BKG",
    "diamond trust bank":            "DTK",
    "equity group":                  "EQTY",
    "family bank":                   "FMLY",
    "hfck group":                    "HFCK",
    "hfcb group":                    "HFCK",   # OCR variant (K misread as B)
    "i&m group":                     "IMH",
    "t&m group":                     "IMH",    # OCR variant (I misread as T)
    "4m group":                      "IMH",    # OCR variant (I misread as 4)
    "kcb group":                     "KCB",
    "ncba group":                    "NCBA",
    "stanbic holdings":              "SBIC",   # FIX: was wrongly mapped to SLAM
    "standard chartered bank kenya": "SCBK",
    "co-operetive bank":             "COOP",
    "co-operative bank":             "COOP",
    "cooperative bank":              "COOP",
    # Commercial
    "deacons":                       "DCON",
    "deacens":                       "DCON",   # OCR variant
    "eveready east africa":          "EVRD",
    "express kenya":                 "XPRS",
    "homeboyz entertainment":        "HMBY",
    "kenya airways":                 "KQ",
    "longhorn publishers":           "LKL",
    "nairobi business ventures":     "NBV",
    "nation media":                  "NMG",
    "sameer africa":                 "SMAF",
    "standard group":                "SGL",
    "tps eastern africa":            "TPSE",
    "uchumi supermarket":            "UCHM",
    "wpp scangroup":                 "SCAN",
    # Construction
    "e.a.portland":                  "PORT",
    "portland cement":               "PORT",
    "bamburi":                       "BAMB",
    "crown paints":                  "CRWN",
    "east african cables":           "CABL",
    # Energy
    "kenolkobil":                    "KNL",
    "kengen":                        "KEGN",
    "kenol":                         "KNL",
    "totalenergies":                 "TOTL",   # OCR variant (no space)
    "total energies":                "TOTL",
    "total kenya":                   "TOTL",
    "kenya pipeline":                "KPC",    # NEW: was missing entirely
    # Insurance
    "britam":                        "BRIT",
    "brito":                         "BRIT",   # OCR variant
    "brita":                         "BRIT",   # OCR variant
    "cic insurance":                 "CIC",
    "ctc insurance":                 "CIC",    # OCR variant (I misread as T)
    "jubilee holdings":              "JUB",
    "kenya re insurance":            "KNRE",
    "kenya re":                      "KNRE",
    "liberty kenya":                 "LBTY",
    "madison insurance":             "MASD",
    "pan africa insurance":          "PAN",
    "sanlam allianz":                "SLAM",   # NEW: company rebranded from Sanlam Kenya
    "sanlam kenya":                  "SLAM",   # legacy name
    # Investment
    "centum":                        "CTUM",
    "home afrika":                   "HAFR",
    "kurwitu":                       "KURV",
    "olympia capital":               "OCH",
    "glympia capital":               "OCH",
    "trans-century":                 "TCL",
    "nairobi securities exchange":   "NSE",
    "nse plc":                       "NSE",
    # Manufacturing
    "b.o.c kenya":                   "BOC",
    "boc kenya":                     "BOC",
    "british american tobacco":      "BAT",
    "carbacid":                      "CARB",
    "east african breweries":        "EABL",
    "flame tree":                    "FTGH",
    "unga group":                    "UNGA",
    "umeme":                         "UMME",
    "mumias sugar":                  "MSC",
    "athi river":                    "ARML",
    "kenya power":                   "KPLC",
    "shri krishna":                  "SHKL",
    "shri krishana":                 "SHKL",   # OCR variant (extra a)
    "africa mega agricorp":          "AMAC",
    # Telecom
    "safaricom":                     "SCOM",
    # REITs
    "acorn d reit":                  "ACRD",
    "acorn t reit":                  "ACRT",
    "ilam fahari":                   "ILAM",
    "laptrust":                      "LPTR",
    "trific":                        "TRFC",
    "alp industrial":                "ALP",
    # ETFs — skip
    "absa new gold":                 "__ETF__",
    "satrix msci":                   "__ETF__",
}

# Stocks whose OCR prices are consistently 100x inflated.
# Values: per-ticker threshold above which the raw price is divided by 100.
# Low thresholds (5.0) for sub-1 KES stocks; higher thresholds (20.0) for
# stocks that legitimately trade up to ~15 KES but OCR drops the decimal point.
_INFLATION_TICKERS: dict[str, float] = {
    "EVRD": 5.0,
    "HAFR": 5.0,
    "UCHM": 5.0,
    "CIC":  20.0,  # normally 3-7 KES; OCR sometimes reads 300-700
}

# Pre-sorted once at module load for greedy longest-first matching
_NSE_PHRASES_SORTED: list[str] = sorted(NSE_PHRASES, key=len, reverse=True)


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

def build_pdf_url(date: datetime.date) -> str:
    month = date.strftime("%b").upper()
    day   = date.strftime("%d")
    year  = date.strftime("%y")
    return f"https://www.nse.co.ke/wp-content/uploads/{day}-{month}-{year}.pdf"


# ---------------------------------------------------------------------------
# Number utilities
# ---------------------------------------------------------------------------

def clean_number(raw: str) -> float:
    cleaned = re.sub(r"[,%]", "", str(raw).strip())
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _extract_numbers(line: str) -> list[float]:
    """Extract all positive numbers from an OCR line."""
    # Replace dot-as-thousands separator (e.g. 5.105.845 → 5105845)
    cleaned = re.sub(r"(\d)\.(\d{3})(?=[.,\d])", r"\1\2", line)
    tokens = re.findall(r"\b\d{1,3}(?:,\d{3})*(?:\.\d{1,4})?\b", cleaned)
    result: list[float] = []
    for t in tokens:
        try:
            v = float(t.replace(",", ""))
            if v > 0:
                result.append(v)
        except ValueError:
            pass
    return result


def _fix_decimal_vs_peers(values: list[float]) -> list[float]:
    """
    Correct 100x OCR scale errors (e.g. 61.25 → 6125).

    Two passes:
    1. Min-reference: if any value is ≥80x the smallest, it is 100x inflated.
       Threshold is 80 (not 50) to avoid false corrections when an "Ord X.00"
       face-value (e.g. 1.00, 5.00) leaks into the number sequence and becomes
       the reference — a valid 69 KES stock (I&M, 69/1=69 < 80) or a 291 KES
       stock (Stanbic, 291/5=58 < 80) would otherwise be wrongly divided.
    2. Consensus: if the majority of values agree on a scale, fix outliers.
       Handles the case where ALL values are inflated (min-reference misses it).
    """
    positives = [v for v in values if v > 0]
    if len(positives) < 2:
        return values

    # Pass 1 — min-reference (threshold 80x)
    ref = min(positives)
    fixed = [round(v / 100, 4) if (v > 0 and v / ref >= 80) else v for v in values]

    # Pass 2 — consensus: if most values are >30x the median after pass 1,
    # ALL of them are still inflated (pass 1 missed because min was also inflated).
    pos2 = [v for v in fixed if v > 0]
    if len(pos2) >= 2:
        median2 = sorted(pos2)[len(pos2) // 2]
        if median2 > 0 and all(v / median2 < 3 for v in pos2):
            # values are now consistent — check if the whole group is 100x a sane range
            # A sane NSE price is < 2000 KES; if median > 2000, divide everything
            if median2 > 2000:
                fixed = [round(v / 100, 4) if v > 0 else v for v in fixed]

    return fixed


def _apply_inflation(ticker: str, price: float) -> float:
    threshold = _INFLATION_TICKERS.get(ticker)
    if threshold is not None and price > threshold:
        return round(price / 100, 4)
    return price


# ---------------------------------------------------------------------------
# Table-mode helpers (fallback for text-selectable PDFs)
# ---------------------------------------------------------------------------

def resolve_ticker(company_name: str) -> str | None:
    upper = company_name.strip().upper()
    for fragment, ticker in COMPANY_TO_TICKER.items():
        if fragment in upper:
            return ticker
    return None


def parse_price_row(row: list[str]) -> dict:
    if len(row) < 9:
        raise ValueError(f"Expected ≥9 columns, got {len(row)}")
    return {
        "prev_close": clean_number(row[COL_PREV_CLOSE]),
        "open":       clean_number(row[COL_OPEN]),
        "high":       clean_number(row[COL_HIGH]),
        "low":        clean_number(row[COL_LOW]),
        "close":      clean_number(row[COL_CLOSE]),
        "change":     clean_number(row[COL_CHANGE]),
        "pct_change": clean_number(row[COL_PCT_CHANGE]),
        "volume":     clean_number(row[COL_VOLUME]),
        "value":      clean_number(row[COL_VALUE]),
    }


# ---------------------------------------------------------------------------
# OCR-mode helpers
# ---------------------------------------------------------------------------

def _match_line_ocr(line: str) -> str | None:
    """Return NSE ticker for this OCR line, or None. '__ETF__' means skip."""
    low = line.lower()
    for phrase in _NSE_PHRASES_SORTED:
        if phrase in low:
            return NSE_PHRASES[phrase]
    return None


def _is_data_line(line: str) -> bool:
    """OCR data rows start with a numeric 52WK_HIGH value and have ≥6 numbers."""
    stripped = line.strip()
    if not stripped or not re.match(r"^\d", stripped):
        return False
    return len(_extract_numbers(stripped)) >= 6


def _parse_ocr_row(line: str, ticker: str) -> dict | None:
    """
    Parse an OCR stock row.
    Structure: 52WK_H  52WK_L  <name+ISIN>  DAY_H  DAY_L  DAY_C  PREV  VOL
    Strategy: use last 5 numbers = DAY_H, DAY_L, DAY_C, PREV_CLOSE, VOL.
    """
    nums = _extract_numbers(line)
    if len(nums) < 6:
        return None

    day_h_raw, day_l_raw, day_c_raw, prev_raw, vol_raw = nums[-5:]

    prices_fixed = _fix_decimal_vs_peers([day_h_raw, day_l_raw, day_c_raw, prev_raw])
    day_h, day_l, day_c, prev_close = prices_fixed

    day_h = _apply_inflation(ticker, day_h)
    day_l = _apply_inflation(ticker, day_l)
    day_c = _apply_inflation(ticker, day_c)

    if day_h < day_l:
        day_h, day_l = day_l, day_h

    volume = int(vol_raw)

    if day_h <= 0 or day_l <= 0 or day_c <= 0 or volume < 1:
        return None
    if day_c < day_l * 0.7 or day_c > day_h * 1.4:
        return None

    # Cross-validate close against prev_close from the PDF.
    # The PDF's prev_close is NSE's official previous close — a reliable anchor.
    # A ≥5× deviation almost always indicates an OCR decimal error or mis-parsed row.
    if prev_close > 0:
        pc_ratio = max(day_c / prev_close, prev_close / day_c)
        if pc_ratio >= 5.0:
            log.warning(
                "  [PREV_CLOSE_MISMATCH] %s: close %.4f is %.1f× prev_close %.4f — row rejected",
                ticker, day_c, pc_ratio, prev_close,
            )
            return None
        if pc_ratio >= 2.0:
            log.warning(
                "  [LARGE_MOVE] %s: close %.4f is %.1f× prev_close %.4f — verify manually",
                ticker, day_c, pc_ratio, prev_close,
            )

    return {
        "prev_close": prev_close,
        "open":       day_c,      # open not separately reported in NSE daily PDF
        "high":       day_h,
        "low":        day_l,
        "close":      day_c,
        "change":     0.0,
        "pct_change": 0.0,
        "volume":     float(volume),
        "value":      0.0,
    }


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def download_pdf(url: str) -> bytes:
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# Core extraction — tries table mode first, falls back to OCR
# ---------------------------------------------------------------------------

def extract_price_rows(pdf_bytes: bytes, resolution: int = 250) -> list[tuple[str, dict]]:
    """
    Returns [(company_name_or_ticker, fields), ...] for all price rows.

    For NSE scanned-image PDFs, pdfplumber.extract_tables() returns nothing;
    the function falls back to pytesseract OCR.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        os.write(tmp_fd, pdf_bytes)
        os.close(tmp_fd)

        results: list[tuple[str, dict]] = []

        # --- Attempt 1: structured table extraction (text-selectable PDFs) ---
        with pdfplumber.open(tmp_path) as pdf:
            table_rows_found = 0
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        if not row or len(row) < 9:
                            continue
                        company = str(row[0] or "").strip()
                        if not company or company.upper() in ("SECURITY", "COMPANY", ""):
                            continue
                        try:
                            float(re.sub(r"[,]", "", str(row[1] or "0")))
                        except (ValueError, TypeError):
                            continue
                        results.append((company, parse_price_row([str(c or "0") for c in row])))
                        table_rows_found += 1

            if table_rows_found > 0:
                log.info("Table mode: extracted %d rows", table_rows_found)
                return results

        # --- Attempt 2: OCR (scanned-image PDFs) ---
        log.info("No tables found — switching to OCR (resolution=%d dpi)", resolution)
        seen: set[str] = set()

        unmatched_lines: list[str] = []
        with pdfplumber.open(tmp_path) as pdf:
            for page in pdf.pages:
                img = page.to_image(resolution=resolution).original
                text = pytesseract.image_to_string(img, config="--psm 6 --oem 3")
                for line in text.split("\n"):
                    line = line.strip()
                    if not line or not _is_data_line(line):
                        continue
                    ticker = _match_line_ocr(line)
                    if ticker == "__ETF__":
                        continue
                    if not ticker:
                        unmatched_lines.append(line)
                        log.warning("  [UNMATCHED] %s", line[:120])
                        continue
                    if ticker in seen:
                        continue
                    fields = _parse_ocr_row(line, ticker)
                    if not fields:
                        log.warning("  [PARSE_FAIL] %s -> %s", ticker, line[:80])
                        continue
                    seen.add(ticker)
                    results.append((ticker, fields))
                    log.info(
                        "  %-6s H=%.2f L=%.2f C=%.2f vol=%.0f",
                        ticker, fields["high"], fields["low"], fields["close"], fields["volume"],
                    )

        if unmatched_lines:
            log.warning(
                "%d unmatched data lines — add OCR phrase variants for these companies",
                len(unmatched_lines),
            )

        return results
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# RTDB writer
# ---------------------------------------------------------------------------

def write_to_rtdb(root_ref, date_str: str, rows: list[tuple[str, dict]], dry_run: bool) -> int:
    from pipeline.scripts.firebase_rtdb import write_price_node
    written = 0
    unknown = []
    for company_name, fields in rows:
        # In OCR mode company_name IS already a ticker; in table mode resolve it
        ticker = company_name if len(company_name) <= 6 else resolve_ticker(company_name)
        if not ticker:
            unknown.append(company_name)
            continue
        node = {
            "o":   fields["open"],
            "h":   fields["high"],
            "l":   fields["low"],
            "c":   fields["close"],
            "v":   fields["volume"],
            "pc":  fields["prev_close"],
            "ch":  fields["change"],
            "pch": fields["pct_change"],
            "vv":  fields["value"],
        }
        if not dry_run:
            write_price_node(root_ref, ticker, date_str, node)
        log.info("  %s: close=%.2f vol=%.0f", ticker, fields["close"], fields["volume"])
        written += 1
    if unknown:
        log.warning("Unknown company names: %s", unknown)
    return written


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",    help="YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pdf",     help="Local PDF path (skip download)")
    parser.add_argument("--resolution", type=int, default=250,
                        help="OCR resolution in DPI (default: 250)")
    args = parser.parse_args()

    target_date = (
        datetime.date.fromisoformat(args.date)
        if args.date
        else datetime.date.today()
    )
    date_str = target_date.isoformat()

    # NSE is closed on weekends — skip unless a specific date was given explicitly
    if not args.date and target_date.weekday() >= 5:
        log.info("NSE closed today (%s). Use --date to backfill. Exiting.", target_date.strftime("%A %Y-%m-%d"))
        return

    if args.pdf:
        pdf_bytes = Path(args.pdf).read_bytes()
        log.info("Using local PDF: %s", args.pdf)
    else:
        url = build_pdf_url(target_date)
        log.info("Downloading %s", url)
        try:
            pdf_bytes = download_pdf(url)
        except requests.HTTPError as exc:
            log.error("PDF not available: %s", exc)
            sys.exit(1)

    rows = extract_price_rows(pdf_bytes, resolution=args.resolution)
    log.info("Extracted %d price rows from PDF", len(rows))

    if not args.dry_run:
        # Import inside branch so dry-run never needs Firebase credentials
        from pipeline.scripts.firebase_client import get_rtdb
        root_ref = get_rtdb()
    else:
        root_ref = None

    written = write_to_rtdb(root_ref, date_str, rows, args.dry_run)
    log.info("Done — wrote %d company records for %s", written, date_str)


if __name__ == "__main__":
    main()
