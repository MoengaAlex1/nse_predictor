"""
NSE PDF Extractor - Step 2 of 2
Reads downloaded PDFs from pipeline/data/pdfs/, extracts financial tables
and key metrics using pdfplumber + PyMuPDF, and writes structured JSON
to pipeline/data/extracted/{safe_ticker}.json ready for seeding.

Usage:
    python pipeline/scripts/extract_pdf_financials.py [--tickers KCB_NR ...] [--all]

Output:
    pipeline/data/extracted/{safe_ticker}.json
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

import pdfplumber
import fitz  # PyMuPDF

PIPELINE_ROOT = Path(__file__).parent.parent
PDF_DIR = PIPELINE_ROOT / "data" / "pdfs"
EXTRACTED_DIR = PIPELINE_ROOT / "data" / "extracted"
MANIFEST_FILE = PDF_DIR / "manifest.json"

# Regex patterns for financial line items
# KES prefix is optional - many PDFs omit it and go straight to number
_KES = r"(?:[Kk][Ee][Ss]?[\s.]*)?"  # optional KES/Kshs prefix
_NUM = r"[\-\(]?" + _KES + r"([\d,]+\.?\d*)\)?"  # optional neg sign + optional KES + number
_BIG = r"([\d,]{5,}\.?\d*)"  # big number: 5+ digit chars (with commas)

# Revenue: "Total Revenue" or "Net Revenue" then whitespace then a large number
REVENUE_SIMPLE_RE = re.compile(
    r"(?:total|net)?\s*revenue[s]?\s*[\r\n\s:]{0,10}" + _BIG,
    re.IGNORECASE,
)
PAT_RE = re.compile(
    r"(?:profit|loss)\)?\s+(?:for\s+the\s+(?:year|period)|after\s+(?:income\s+)?tax)[\s:]*" + _KES + r"\(?([\d,]+\.?\d*)\)?",
    re.IGNORECASE,
)
NET_INCOME_RE = re.compile(
    r"(?:net\s+(?:profit|income|earnings?))[\s:]*" + _KES + r"\(?([\d,]+\.?\d*)\)?",
    re.IGNORECASE,
)
EPS_RE = re.compile(
    r"earnings?\s+per\s+share(?:\s*\([^)]{0,20}\))?\s*" + _KES + r"\(?([\d.,]+)\)?",
    re.IGNORECASE,
)
DPS_RE = re.compile(
    r"(?:dividend\s+per\s+share|dps|proposed\s+dividend(?:\s+per\s+share)?)[\s:]*" + _KES + r"([\d.,]+)",
    re.IGNORECASE,
)
BVPS_RE = re.compile(
    r"(?:book\s+value\s+per\s+share|nav\s+per\s+share|net\s+assets?\s+per\s+share)[\s:]*" + _KES + r"([\d.,]+)",
    re.IGNORECASE,
)
PERIOD_RE = re.compile(
    r"(?:year|period|six\s+months?|half\s+year)\s+(?:ended?|ending)\s+"
    r"(\d{1,2}[\s\-]\w+[\s\-]\d{4}|\d{4}-\d{2}-\d{2}|\w+\s+\d{4}|\d{2}-\w{3}-\d{2,4})",
    re.IGNORECASE,
)
# Matches "31-Mar-26", "31 March 2026" etc.
DATE_COMPACT_RE = re.compile(
    r"\b(\d{1,2})[\-/](jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\-/](\d{2,4})\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b(3[01]|[12]\d|0?\d)\s+(january|february|march|april|may|june|"
                     r"july|august|september|october|november|december)\s+(\d{4})\b",
                     re.IGNORECASE)

MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def parse_kes_number(raw: str) -> Optional[float]:
    """Convert '123,456,789' to 123456789.0. Returns None if unparseable."""
    try:
        return float(raw.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def to_kes_mn(value: Optional[float]) -> Optional[float]:
    """Scale raw number to KES millions. Returns None if value looks implausible."""
    if value is None:
        return None
    if value >= 1_000_000:
        mn = round(value / 1_000, 1)  # assume Kshs 000
    elif value >= 1_000:
        mn = round(value, 1)  # already in millions
    else:
        return round(value, 2)  # EPS/per-share scale
    # Sanity: no Kenyan company has revenue or PAT > KES 5 trillion
    if abs(mn) > 5_000_000:
        return None
    return mn


_MONTH_ABBR = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def parse_date_str(raw: str) -> Optional[str]:
    """Parse '31 December 2023', '31-Mar-26', '31-Mar-2026' to 'YYYY-MM-DD'."""
    raw = raw.strip()
    # Try YYYY-MM-DD
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    # Full month name: "31 December 2023"
    m = DATE_RE.search(raw)
    if m:
        day, month_str, year = m.group(1), m.group(2).lower(), m.group(3)
        month = MONTHS.get(month_str)
        if month:
            return f"{year}-{month}-{int(day):02d}"
    # Compact: "31-Mar-26" or "31-Mar-2026"
    m = DATE_COMPACT_RE.search(raw)
    if m:
        day, month_abbr, year = m.group(1), m.group(2).lower()[:3], m.group(3)
        month = _MONTH_ABBR.get(month_abbr)
        if month:
            yr = int(year)
            yr = 2000 + yr if yr < 100 else yr
            return f"{yr}-{month}-{int(day):02d}"
    return None


def extract_text_pymupdf(pdf_path: Path) -> str:
    """Fast full-text extraction using PyMuPDF."""
    try:
        doc = fitz.open(str(pdf_path))
        pages = []
        for page in doc:
            pages.append(page.get_text("text"))
        doc.close()
        return "\n".join(pages)
    except Exception as e:
        print(f"    PyMuPDF error: {e}")
        return ""


def extract_tables_pdfplumber(pdf_path: Path) -> list[list[list[str]]]:
    """Extract all tables from PDF using pdfplumber. Returns list of tables."""
    tables = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)
    except Exception as e:
        print(f"    pdfplumber error: {e}")
    return tables


def search_text_for_metrics(text: str) -> dict:
    """Scan full text with regex to pull key financial metrics."""
    result: dict = {}

    m = REVENUE_SIMPLE_RE.search(text)
    if m:
        val = parse_kes_number(m.group(1))
        if val and val > 100:  # sanity: must be >100 (not EPS-scale)
            result["revenue_raw"] = val

    for pattern in [PAT_RE, NET_INCOME_RE]:
        m = pattern.search(text)
        if m:
            result["net_income_raw"] = parse_kes_number(m.group(1))
            # Check if preceded by "Loss" - negative
            match_start = m.start()
            context = text[max(0, match_start - 10):match_start + 5].lower()
            if "loss" in context or "(" in m.group(0):
                result["net_income_negative"] = True
            break

    m = EPS_RE.search(text)
    if m:
        val = parse_kes_number(m.group(1))
        if val and val < 5000:  # EPS should not be in millions
            result["eps_raw"] = val

    m = DPS_RE.search(text)
    if m:
        val = parse_kes_number(m.group(1))
        if val and val < 5000:
            result["dps_raw"] = val

    m = BVPS_RE.search(text)
    if m:
        val = parse_kes_number(m.group(1))
        if val and val < 100_000:
            result["bvps_raw"] = val

    # Period end date - try PERIOD_RE first, then compact date in first 500 chars
    m = PERIOD_RE.search(text)
    if m:
        result["period_raw"] = m.group(1)
        result["period_end"] = parse_date_str(m.group(1))
    else:
        # Fallback: look for a compact date like "31-Mar-26" near the top
        m2 = DATE_COMPACT_RE.search(text[:2000])
        if m2:
            raw = m2.group(0)
            result["period_raw"] = raw
            result["period_end"] = parse_date_str(raw)

    return result


def search_tables_for_metrics(tables: list[list[list[str]]]) -> dict:
    """Scan extracted tables for financial line items."""
    result: dict = {}

    for table in tables:
        for row in table:
            if not row:
                continue
            # Flatten row to string for searching
            row_text = " ".join(str(c or "") for c in row).strip()
            row_lower = row_text.lower()

            # Look for revenue row
            if any(kw in row_lower for kw in ["revenue", "turnover"]) and not result.get("revenue_raw"):
                # Find first numeric cell in row
                for cell in row[1:]:
                    val = parse_kes_number(str(cell or ""))
                    if val and val > 0:
                        result["revenue_raw"] = val
                        break

            # Look for PAT / net profit row
            if (("profit" in row_lower or "net income" in row_lower)
                    and ("after tax" in row_lower or "for the year" in row_lower or "for the period" in row_lower)
                    and not result.get("net_income_raw")):
                for cell in row[1:]:
                    raw = str(cell or "").replace("(", "-").replace(")", "")
                    val = parse_kes_number(raw)
                    if val is not None:
                        result["net_income_raw"] = abs(val)
                        if raw.strip().startswith("-") or "(" in str(cell or ""):
                            result["net_income_negative"] = True
                        break

            # EPS
            if "earnings per share" in row_lower or ("eps" in row_lower and "basic" in row_lower):
                for cell in row[1:]:
                    val = parse_kes_number(str(cell or ""))
                    if val is not None and val < 1000:
                        result["eps_raw"] = val
                        break

            # DPS
            if "dividend per share" in row_lower or "proposed dividend" in row_lower:
                for cell in row[1:]:
                    val = parse_kes_number(str(cell or ""))
                    if val is not None and val < 1000:
                        result["dps_raw"] = val
                        break

            # BVPS
            if ("book value per share" in row_lower or "nav per share" in row_lower
                    or "net assets per share" in row_lower):
                for cell in row[1:]:
                    val = parse_kes_number(str(cell or ""))
                    if val is not None and val < 10000:
                        result["bvps_raw"] = val
                        break

    return result


def infer_period_type(filename: str, text: str) -> str:
    text_lower = (filename + " " + text[:2000]).lower()
    if any(kw in text_lower for kw in ["half year", "six months", "interim", "h1", "h2", "quarter"]):
        return "interim"
    return "annual"


def infer_period_label(period_end: Optional[str], filename: str) -> str:
    if period_end:
        year = period_end[:4]
        month = int(period_end[5:7])
        if month in (12, 1):
            return f"FY{year}"
        elif month == 3:
            return f"FY{year} (Mar)"
        elif month == 6:
            return f"FY{year} (Jun)"
        elif month == 9:
            return f"FY{year} (Sep)"
        else:
            return f"FY{year}"
    # Fallback: find year in filename
    m = re.search(r"(20\d{2})", filename)
    return f"FY{m.group(1)}" if m else "Unknown"


def extract_one_pdf(pdf_path: Path) -> dict:
    """Extract metrics from a single PDF file."""
    print(f"    Extracting: {pdf_path.name}")

    # Text extraction (fast)
    text = extract_text_pymupdf(pdf_path)
    text_metrics = search_text_for_metrics(text)

    # Table extraction (slower but more accurate for structured tables)
    tables = extract_tables_pdfplumber(pdf_path)
    table_metrics = search_tables_for_metrics(tables)

    # Merge: table metrics win over text regex where both found
    merged = {**text_metrics, **{k: v for k, v in table_metrics.items() if v is not None}}

    period_type = infer_period_type(pdf_path.name, text)
    period_end = merged.get("period_end")
    period_label = infer_period_label(period_end, pdf_path.name)

    # Scale raw numbers to KES millions
    revenue_mn = to_kes_mn(merged.get("revenue_raw"))
    net_income_mn = to_kes_mn(merged.get("net_income_raw"))
    if merged.get("net_income_negative") and net_income_mn is not None:
        net_income_mn = -net_income_mn

    eps = merged.get("eps_raw")
    dps = merged.get("dps_raw")
    bvps = merged.get("bvps_raw")

    return {
        "pdf_file": pdf_path.name,
        "period": period_label,
        "period_end": period_end,
        "period_type": period_type,
        "revenue_kes_mn": revenue_mn,
        "net_income_kes_mn": net_income_mn,
        "eps": eps,
        "dps": dps,
        "bvps": bvps,
        "raw_period_text": merged.get("period_raw"),
        "pages_extracted": len(tables),
        "text_length": len(text),
    }


def process_ticker(safe_ticker: str, manifest: dict) -> Optional[dict]:
    ticker_dir = PDF_DIR / safe_ticker
    if not ticker_dir.exists():
        print(f"  [skip] No PDF directory for {safe_ticker}")
        return None

    ticker_info = manifest.get(safe_ticker, {})
    files_meta = ticker_info.get("files", {})

    pdf_files = sorted(ticker_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"  [skip] No PDFs in {ticker_dir}")
        return None

    print(f"\n[{safe_ticker}] {ticker_info.get('name', '')} - {len(pdf_files)} PDF(s)")
    results = []
    for pdf_path in pdf_files:
        try:
            metrics = extract_one_pdf(pdf_path)
            if any(v is not None for v in [
                metrics["revenue_kes_mn"],
                metrics["net_income_kes_mn"],
                metrics["eps"],
            ]):
                results.append(metrics)
                print(f"      Revenue: {metrics['revenue_kes_mn']} mn | "
                      f"PAT: {metrics['net_income_kes_mn']} mn | "
                      f"EPS: {metrics['eps']} | Period: {metrics['period']}")
            else:
                print(f"      No financial data extracted from {pdf_path.name}")
        except Exception as e:
            print(f"      Error processing {pdf_path.name}: {e}")

    return {"ticker": safe_ticker, "name": ticker_info.get("name", ""), "extracted": results}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Extract financials from NSE PDFs")
    parser.add_argument("--tickers", nargs="*", help="Specific safe_tickers")
    parser.add_argument("--all", action="store_true", default=True, help="Process all")
    args = parser.parse_args()

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    if not MANIFEST_FILE.exists():
        print("No manifest found. Run scrape_nse_pdfs.py first.")
        sys.exit(1)

    with open(MANIFEST_FILE, encoding="utf-8") as f:
        manifest = json.load(f)

    tickers = args.tickers if args.tickers else list(manifest.keys())
    print(f"Extracting from {len(tickers)} ticker(s)...")

    summary = {}
    for safe_ticker in tickers:
        result = process_ticker(safe_ticker, manifest)
        if result and result["extracted"]:
            summary[safe_ticker] = result
            out_file = EXTRACTED_DIR / f"{safe_ticker}.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"  Saved -> {out_file.name}")

    # Write combined summary
    combined_file = EXTRACTED_DIR / "all_extracted.json"
    with open(combined_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"\n=== Done ===")
    print(f"Extracted data for {len(summary)} tickers")
    print(f"Combined output: {combined_file}")


if __name__ == "__main__":
    main()
