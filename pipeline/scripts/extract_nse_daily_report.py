"""
extract_nse_daily_report.py

OCR-extract daily closing prices from NSE daily trading report PDFs.
Scanned-image PDFs (no selectable text).

Column order after company info: DAY_HIGH  DAY_LOW  DAY_CLOSE  PREV_CLOSE  VOLUME
(Confirmed: PREV_CLOSE on day N+1 == DAY_CLOSE on day N, validated against Safaricom rows.)

Usage:
    python pipeline/scripts/extract_nse_daily_report.py
        --pdfs 21-JUL-26.pdf 22-JUL-26.pdf 23-JUL-26.pdf
        [--dry-run]
        [--resolution 250]
"""

import argparse
import csv
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber
import pytesseract

PIPELINE_ROOT = Path(__file__).parent.parent
DATA_CLEANED = PIPELINE_ROOT.parent / "data" / "cleaned"
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FIELDNAMES = ["Date", "Open", "High", "Low", "Close", "Volume", "Is_Stale", "Ticker"]

# Stocks whose prices are 100x inflated from 2026-01-01 onward
INFLATION_TICKERS = {"EVRD", "HAFR", "UCHM"}

# Unique search phrases for each NSE ticker.
# Ordered longest-first for greedy matching.
# Keys are lowercase substrings expected in the OCR line.
NSE_PHRASES: dict[str, str] = {
    # Agricultural
    "enagad": "EGAD",
    "kakuzi": "KUKZ",
    "kopackhora tea": "KAPC",
    "limuru tea": "LIMT",
    "sasini": "SASN",
    "williamson tea": "WTK",
    # Automobiles
    "car and general": "CGEN",
    # Banking
    "absa bank": "ABSA",
    "bk group": "BKG",
    "diamond trust bank": "DTK",
    "equity group": "EQTY",
    "family bank": "FMLY",
    "hfck group": "HFCK",
    "i&m group": "IMH",
    "kcb group": "KCB",
    "ncba group": "NCBA",
    "stanbic holdings": "SLAM",
    "standard chartered bank kenya": "SCBK",
    "co-operetive bank": "COOP",
    "co-operative bank": "COOP",
    "cooperative bank": "COOP",
    # Commercial
    "deacons": "DCON",
    "eveready east africa": "EVRD",
    "express kenya": "XPRS",
    "homeboyz entertainment": "HMBY",
    "kenya airways": "KQ",
    "longhorn publishers": "LKL",
    "nairobi business ventures": "NBV",
    "nation media": "NMG",
    "sameer africa": "SMAF",
    "standard group": "SGL",
    "tps eastern africa": "TPSE",
    "uchumi supermarket": "UCHM",
    "wpp scangroup": "SCAN",
    # Construction
    "e.a.portland": "PORT",
    "portland cement": "PORT",
    "bamburi": "BAMB",
    "crown paints": "CRWN",
    "east african cables": "CABL",
    # Energy
    "kenolkobil": "KNL",
    "kengen": "KEGN",
    "kenol": "KNL",
    "hotaln": "HDEV",
    "total energies": "TOTL",
    "total kenya": "TOTL",
    # Insurance
    "britam": "BRIT",
    "cic insurance": "CIC",
    "jubilee holdings": "JUB",
    "kenya re insurance": "KNRE",
    "kenya re": "KNRE",
    "liberty kenya": "LBTY",
    "madison insurance": "MASD",
    "pan africa insurance": "PAN",
    "sanlam kenya": "SLAM",
    # Investment
    "centum": "CTUM",
    "home afrika": "HAFR",
    "kurwitu": "KURV",
    "olympia capital": "OCH",
    "trans-century": "TCL",
    "nairobi securities exchange": "NSE",
    "nse plc": "NSE",
    # Manufacturing
    "b.o.c kenya": "BOC",
    "boc kenya": "BOC",
    "british american tobacco": "BAT",
    "carbacid": "CARB",
    "east african breweries": "EABL",
    "flame tree": "FTGH",
    "unga group": "UNGA",
    "umeme": "UMME",
    "mumias sugar": "MSC",
    "athi river": "ARML",
    "shri krishna": "SHKL",
    "africa mega agricorp": "AMAC",
    # Telecom
    "safaricom": "SCOM",
    # REITs
    "acorn d reit": "ACRD",
    "acorn t reit": "ACRT",
    "ilam fahari": "ILAM",
    "laptrust": "LPTR",
    "trific": "TRFC",
    "alp industrial": "ALP",
    # ETFs — listed separately to AVOID matching them as stocks
    "absa new gold": "__ETF__",
    "satrix msci": "__ETF__",
}


def _parse_filename_date(pdf_path: Path) -> str:
    stem = pdf_path.stem.upper()
    for fmt in ("%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(stem, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date from: {pdf_path.name}")


def _fix_decimal_vs_peers(values: list[float]) -> list[float]:
    """
    OCR sometimes drops decimal points (e.g. '174.75' → '17475').
    Fix by using the minimum non-zero value as the reference scale:
    any value ≥ 50× the minimum is assumed to be 100× inflated and is divided by 100.
    Using MIN (not median) ensures correction works even when most prices are wrong.
    """
    positives = [v for v in values if v > 0]
    if len(positives) < 2:
        return values
    ref = min(positives)
    if ref <= 0:
        return values
    result = []
    for v in values:
        if v > 0 and v / ref >= 50:
            result.append(round(v / 100, 4))
        else:
            result.append(v)
    return result


def _apply_inflation(ticker: str, price: float) -> float:
    if ticker in INFLATION_TICKERS and price > 5.0:
        return round(price / 100, 4)
    return price


def _extract_numbers(line: str) -> list[float]:
    """
    Extract all positive numbers from a line.
    Handles: '33.40', '181,641', '1,879,242', '5.105.845' (period-thousands).
    """
    # Replace dot-as-thousands (e.g. 5.105.845 → 5105845) only when followed by 3 digits and another dot/end
    # But leave decimal-point dots alone (e.g. 33.40 has only one dot and < 3 pre-dot digits)
    cleaned = re.sub(r'(\d)\.(\d{3})(?=[.,\d])', r'\1\2', line)  # "5.105.845" → "5105845"

    # Match: optional-comma-thousands integer optionally followed by decimal part
    tokens = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d{1,4})?\b', cleaned)
    result: list[float] = []
    for t in tokens:
        try:
            v = float(t.replace(",", ""))
            if v > 0:
                result.append(v)
        except ValueError:
            pass
    return result


def _match_line(line: str) -> str | None:
    """Return NSE ticker code or None. Returns '__ETF__' for ETF lines to skip them."""
    low = line.lower()
    # Try longest phrase first (more specific wins)
    for phrase in sorted(NSE_PHRASES, key=len, reverse=True):
        if phrase in low:
            return NSE_PHRASES[phrase]
    return None


def _is_data_line(line: str) -> bool:
    """
    Stock rows start with the 52WK HIGH value (a decimal price).
    Lines starting with text (section headers, corporate actions) are excluded.
    """
    stripped = line.strip()
    if not stripped:
        return False
    # Must start with a number (52WK high)
    if not re.match(r'^\d', stripped):
        return False
    nums = _extract_numbers(stripped)
    return len(nums) >= 6


def parse_stock_row(line: str, ticker: str) -> dict | None:
    """
    Parse a stock row into {high, low, close, volume}.

    Line structure:
      52WK_H  52WK_L  <company name + ISIN + code + status>  DAY_H  DAY_L  DAY_C  PREV  VOL

    Strategy: last 5 tokens = DAY_H, DAY_L, DAY_C, PREV, VOL.
    Fix OCR-dropped decimals by comparing values against their peers.
    """
    nums = _extract_numbers(line)
    if len(nums) < 6:
        return None

    last5 = nums[-5:]
    day_h_raw, day_l_raw, day_c_raw, prev_raw, vol_raw = last5

    # Fix 100× scale errors in the 4 price values (not volume)
    prices_fixed = _fix_decimal_vs_peers([day_h_raw, day_l_raw, day_c_raw, prev_raw])
    day_h, day_l, day_c = prices_fixed[0], prices_fixed[1], prices_fixed[2]

    # Apply 100x inflation correction for EVRD / HAFR
    day_h = _apply_inflation(ticker, day_h)
    day_l = _apply_inflation(ticker, day_l)
    day_c = _apply_inflation(ticker, day_c)

    volume = int(vol_raw)

    # Swap if OCR flipped high and low
    if day_h < day_l:
        day_h, day_l = day_l, day_h

    # Sanity checks
    if day_h <= 0 or day_l <= 0 or day_c <= 0 or volume < 1:
        return None
    if day_c < day_l * 0.7 or day_c > day_h * 1.4:
        return None

    return {"high": day_h, "low": day_l, "close": day_c, "volume": volume}


def ocr_lines(path: Path, resolution: int = 250) -> list[str]:
    lines: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            img = page.to_image(resolution=resolution).original
            text = pytesseract.image_to_string(img, config="--psm 6 --oem 3")
            lines.extend(text.split("\n"))
    return lines


def extract_pdf(
    pdf_path: Path,
    companies: list[dict],
    resolution: int = 250,
) -> dict[str, dict]:
    """Return {ticker: {date, ticker, safe, high, low, close, volume}}."""
    date_iso = _parse_filename_date(pdf_path)
    log.info("Extracting %s → %s", pdf_path.name, date_iso)

    # Build ticker → safe mapping
    ticker_to_safe: dict[str, str] = {
        c["ticker"].split(".")[0].upper(): c["ticker"].replace(".", "_")
        for c in companies
    }

    lines = ocr_lines(pdf_path, resolution=resolution)
    results: dict[str, dict] = {}

    for line in lines:
        line = line.strip()
        if not line or not _is_data_line(line):
            continue

        ticker = _match_line(line)
        if not ticker or ticker == "__ETF__":
            continue
        if ticker in results:
            continue

        parsed = parse_stock_row(line, ticker)
        if not parsed:
            continue

        safe = ticker_to_safe.get(ticker, f"{ticker}_NR")
        results[ticker] = {
            "date": date_iso,
            "ticker": ticker,
            "safe": safe,
            **parsed,
        }
        log.info(
            "  %-8s H=%.4f L=%.4f C=%.4f vol=%d",
            ticker, parsed["high"], parsed["low"], parsed["close"], parsed["volume"],
        )

    log.info("Extracted %d stocks from %s", len(results), pdf_path.name)
    return results


def _load_cleaned(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save_cleaned(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def _last_known_close(rows: list[dict], before_date: str) -> float:
    """Return the most recent Close before before_date, or 0."""
    best = 0.0
    for r in reversed(rows):
        if r.get("Date", "") < before_date:
            try:
                v = float(r.get("Close", 0) or 0)
                if v > 0:
                    return v
            except (ValueError, TypeError):
                pass
    return best


def _apply_vs_history(ticker: str, close: float, high: float, low: float, last_close: float) -> tuple[float, float, float]:
    """
    OCR can drop decimal points in either direction: '265' → '2.65' or '1.70' → '170'.
    If new price is ≥ 50× history → divide by 100.
    If new price is ≤ 1/50 history → multiply by 100.
    Stocks in INFLATION_TICKERS are already corrected before this runs.
    """
    if last_close <= 0 or close <= 0:
        return close, high, low
    ratio = close / last_close
    if ratio >= 50:
        factor = 1 / 100
    elif ratio <= 0.02:
        factor = 100
    else:
        return close, high, low

    new_c = round(close * factor, 4)
    new_h = round(high * factor, 4)
    new_l = round(low * factor, 4)

    # Clip h/l when they have their own independent OCR errors
    if new_h > new_c * 2.0 or new_h < new_c:
        new_h = new_c
    if new_l > new_c or new_l < new_c * 0.5:
        new_l = new_c

    direction = "÷100" if factor < 1 else "×100"
    log.info("  %s: history %s %.4f → %.4f (ratio %.1fx)", ticker, direction, close, new_c, abs(ratio if factor < 1 else 1 / ratio))
    return new_c, new_h, new_l


def upsert_to_csv(record: dict, dry_run: bool) -> str:
    safe, ticker, date_iso = record["safe"], record["ticker"], record["date"]
    csv_path = DATA_CLEANED / f"{safe}_cleaned.csv"
    if not csv_path.exists():
        log.warning("No CSV for %s (safe=%s)", ticker, safe)
        return "no_csv"

    rows = _load_cleaned(csv_path)
    date_index = {r.get("Date", "")[:10]: i for i, r in enumerate(rows)}
    existing_idx = date_index.get(date_iso)

    close, high, low = record["close"], record["high"], record["low"]

    last_close = _last_known_close(rows, date_iso)
    close, high, low = _apply_vs_history(ticker, close, high, low, last_close)

    new_row = {
        "Date": date_iso,
        "Open": close,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": record["volume"],
        "Is_Stale": 0,
        "Ticker": ticker,
    }

    if existing_idx is None:
        if not dry_run:
            insert_at = len(rows)
            for i, r in enumerate(rows):
                if r.get("Date", "") > date_iso:
                    insert_at = i
                    break
            rows.insert(insert_at, new_row)
            _save_cleaned(csv_path, rows)
        return "added"

    stored_close = float(rows[existing_idx].get("Close", 0) or 0)
    if abs(stored_close - close) > 0.001:
        if not dry_run:
            rows[existing_idx].update(new_row)
            _save_cleaned(csv_path, rows)
        return "corrected"
    return "unchanged"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdfs", nargs="+", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resolution", type=int, default=250)
    args = parser.parse_args()

    companies = load_companies()
    totals: dict[str, int] = {}

    for pdf_str in args.pdfs:
        pdf_path = Path(pdf_str)
        if not pdf_path.exists():
            log.error("PDF not found: %s", pdf_path)
            continue

        price_data = extract_pdf(pdf_path, companies, args.resolution)

        for ticker, record in sorted(price_data.items()):
            status = upsert_to_csv(record, args.dry_run)
            totals[status] = totals.get(status, 0) + 1
            if status in ("added", "corrected"):
                log.info(
                    "[%s] %s %s close=%.4f",
                    status, record["safe"], record["date"], record["close"],
                )

    print("\n=== PDF Extraction Summary ===")
    if args.dry_run:
        print("DRY RUN — no files written")
    for k, v in sorted(totals.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
