"""
NSE Daily Price Scraper
Downloads the NSE Kenya daily equity price PDF bulletins and extracts
OHLCV data for target tickers, then updates cleaned CSV files.

URL pattern: https://www.nse.co.ke/wp-content/uploads/{DD}-{MON}-{YY}.pdf

Usage:
    python pipeline/scripts/scrape_nse_daily_prices.py [--start 2025-10-01] [--end 2026-07-24]
    python pipeline/scripts/scrape_nse_daily_prices.py --dry-run
    python pipeline/scripts/scrape_nse_daily_prices.py --skip-firestore
"""

import argparse
import io
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import firebase_admin
from firebase_admin import credentials as fb_credentials, firestore as fb_firestore
import json
import os
import pandas as pd
import pdfplumber
import pytesseract
import requests
from PIL import Image

# Disable PIL decompression bomb check — NSE PDFs can render to large images
Image.MAX_IMAGE_PIXELS = None

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PIPELINE_ROOT = ROOT / "pipeline"
DATA_ROOT = ROOT / "data" / "cleaned"
PDF_CACHE_DIR = ROOT / "pipeline" / "data" / "nse_daily_pdfs"
PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Target tickers ─────────────────────────────────────────────────────────────
# ISIN numbers from NSE PDF extractions
TICKERS: dict[str, dict] = {
    "SCOM_NR": {
        "isin": "KE1000001402",
        "search_names": ["Safaricom"],
        "short": "SCOM",
        "listed_from": None,  # always listed
    },
    "NSE_NR": {
        "isin": "KE3000009674",
        "search_names": ["Nairobi Securities Exchange"],
        "short": "NSE",
        "listed_from": None,
    },
    "KURV_NR": {
        "isin": "KE4000001216",
        "search_names": ["Kurwitu"],
        "short": "KURV",
        "listed_from": None,
    },
    "ALP_NR": {
        "isin": None,  # Discovered dynamically
        "search_names": ["ALP Industrial", "ALP I-REIT", "ALP"],
        "short": "ALP",
        "listed_from": "2026-03-01",
    },
    "TRFC_NR": {
        "isin": None,  # Discovered dynamically
        "search_names": ["TRIFIC", "TRFC", "Green USD"],
        "short": "TRFC",
        "listed_from": "2026-06-01",
    },
}

MONTH_MAP = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# ── Discovered ISINs cache (populated at runtime) ──────────────────────────────
_discovered_isins: dict[str, str] = {}


def _pdf_url(d: date) -> str:
    return (
        f"https://www.nse.co.ke/wp-content/uploads/"
        f"{d.day:02d}-{MONTH_MAP[d.month]}-{str(d.year)[2:]}.pdf"
    )


def _pdf_cache_path(d: date) -> Path:
    return PDF_CACHE_DIR / f"{d.day:02d}-{MONTH_MAP[d.month]}-{str(d.year)[2:]}.pdf"


def _trading_days(start: date, end: date) -> list[date]:
    """Return weekdays between start and end inclusive."""
    days = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # Mon=0 … Fri=4
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _download_pdf(d: date, session: requests.Session) -> Optional[bytes]:
    cache = _pdf_cache_path(d)
    if cache.exists():
        return cache.read_bytes()

    url = _pdf_url(d)
    try:
        r = session.get(url, timeout=30)
        if r.status_code == 404:
            return None  # holiday / non-trading day
        if r.status_code != 200:
            print(f"  [{d}] HTTP {r.status_code}")
            return None
        if not r.content[:4] == b"%PDF":
            return None
        cache.write_bytes(r.content)
        return r.content
    except Exception as e:
        print(f"  [{d}] download error: {e}")
        return None


def _is_text_pdf(data: bytes) -> bool:
    """Quick check: does pdfplumber find any text on the first page?"""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = pdf.pages[0].extract_text() or ""
            return len(text) > 100
    except Exception:
        return False


def _extract_text_from_text_pdf(data: bytes) -> str:
    """Extract text from a vector/text-based PDF using pdfplumber."""
    parts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            parts.append(t)
    return "\n".join(parts)


def _pdf_page_to_image(data: bytes, page_idx: int, target_width: int = 2800) -> Image.Image:
    """
    Render a PDF page to a PIL image using PyMuPDF.
    Scales the page so the output width equals target_width regardless of the
    PDF's native resolution (some NSE PDFs embed very high-DPI scans).
    """
    doc = fitz.open(stream=data, filetype="pdf")
    page = doc[page_idx]

    rect = page.rect
    scale = target_width / rect.width
    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img_bytes = pix.tobytes("png")
    return Image.open(io.BytesIO(img_bytes))


def _crop_ocr_section(img: Image.Image, header_word: str, crop_height: int = 200) -> str:
    """
    When full-page PSM-6 OCR misses a single-row section, locate the section
    header by word bounding box and crop-OCR the band below it.

    PSM-6 skips isolated single-row sections (e.g. TELECOMMUNICATION with only
    Safaricom) during block segmentation, but works correctly on a tight crop.
    Returns the extracted text for that crop, or empty string if header not found.
    """
    try:
        d = pytesseract.image_to_data(
            img, lang="eng", config="--psm 6 --oem 3",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return ""

    header_y = None
    for i, word in enumerate(d["text"]):
        if header_word.lower() in word.strip().lower():
            header_y = d["top"][i]
            break

    if header_y is None:
        return ""

    y0 = max(0, header_y - 5)
    y1 = min(img.height, header_y + crop_height)
    crop = img.crop((0, y0, img.width, y1))

    try:
        return pytesseract.image_to_string(crop, lang="eng", config="--psm 6 --oem 3")
    except Exception:
        return ""


def _extract_text_from_image_pdf(data: bytes) -> str:
    """
    OCR all pages of an image-based PDF using pytesseract.
    Primary pass: full-page PSM-6.
    Recovery pass: if SCOM ISIN is absent, locate the TELECOMMUNICATION header
    via word bounding boxes and crop-OCR that section — PSM-6 full-page
    segmentation skips single-row sections but handles tight crops correctly.
    """
    scom_isin = TICKERS["SCOM_NR"]["isin"]
    doc = fitz.open(stream=data, filetype="pdf")
    parts = []
    for page_idx in range(len(doc)):
        img = _pdf_page_to_image(data, page_idx, target_width=2800)
        text = pytesseract.image_to_string(img, lang="eng", config="--psm 6 --oem 3")

        # Recovery: crop-OCR the TELECOM section when full-page pass misses SCOM
        if scom_isin and scom_isin not in text and "safaricom" not in text.lower():
            crop_text = _crop_ocr_section(img, "TELECOMMUNICATION", crop_height=200)
            if crop_text.strip():
                text += "\n" + crop_text

        parts.append(text)
    return "\n".join(parts)


def _get_pdf_text(data: bytes) -> str:
    if _is_text_pdf(data):
        return _extract_text_from_text_pdf(data)
    return _extract_text_from_image_pdf(data)


# ── Parsing ───────────────────────────────────────────────────────────────────

def _clean_number(s: str) -> Optional[float]:
    """Parse a possibly-formatted number string like '6,186,814' or '29.30'."""
    s = s.strip().replace(",", "")
    # Fix common OCR errors: O→0, l→1 in numeric context
    s = s.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    try:
        return float(s)
    except ValueError:
        return None


def _extract_numbers_after_isin(text_after_isin: str) -> list[float]:
    """
    From the text after the ISIN, extract up to 5 numbers.
    Skips alphabetic status tokens (xd, ed, eq, cb, S, sme, etc.).
    """
    tokens = text_after_isin.split()
    nums: list[float] = []
    for tok in tokens:
        if len(nums) >= 5:
            break
        # Skip pure-alpha tokens (status codes like xd, ed, S, sme)
        tok_stripped = tok.strip(".,;-")
        if tok_stripped.isalpha() and len(tok_stripped) <= 4:
            continue
        n = _clean_number(tok_stripped)
        if n is not None and n > 0:
            nums.append(n)
    return nums


def _normalize_for_isin(text: str) -> str:
    """Normalize OCR-common digit/letter substitutions for ISIN matching."""
    return (
        text.replace("O", "0").replace("o", "0")
            .replace("l", "1").replace("I", "1")
            .replace(" ", "")
    )


def _find_ticker_lines(safe: str, text: str) -> list[str]:
    """
    Return lines from text that most likely contain the price row for `safe`.
    Strategy: primary = ISIN match (with OCR-normalization); fallback = company name.
    """
    cfg = TICKERS[safe]
    isin = cfg["isin"] or _discovered_isins.get(safe)
    lines = text.split("\n")
    candidates: list[str] = []

    # 1. Try exact ISIN match
    if isin:
        for line in lines:
            if isin in line:
                candidates.append(line)
        if candidates:
            return candidates

    # 2. Try OCR-normalized ISIN match
    if isin:
        norm_isin = _normalize_for_isin(isin)
        for line in lines:
            if norm_isin in _normalize_for_isin(line):
                candidates.append(line)
        if candidates:
            return candidates

    # 3. Try company name match (most reliable against OCR errors)
    for name_pat in cfg["search_names"]:
        for line in lines:
            if name_pat.lower() in line.lower():
                # Try to discover ISIN from this line if we don't have one
                if isin is None:
                    m = re.search(r"\b(KE[A-Z0-9]{10})\b", _normalize_for_isin(line))
                    if m:
                        discovered = m.group(1)
                        _discovered_isins[safe] = discovered
                        cfg["isin"] = discovered
                        print(f"    Discovered ISIN for {safe}: {discovered}")
                candidates.append(line)
        if candidates:
            return candidates

    return []


def _parse_numbers_from_line(line: str, isin: Optional[str]) -> list[float]:
    """
    Extract price data numbers from a row line.
    Splits at the ISIN to get numbers after it; falls back to last-N heuristic.
    """
    after = ""

    # 1. Exact ISIN split
    if isin and isin in line:
        after = line.split(isin)[-1]
    else:
        # 2. Find any KE-ISIN pattern with OCR tolerance (I/1, O/0 swaps)
        isin_match = re.search(r"[Kk][Ee][0-9A-Za-z]{10}", line)
        if isin_match:
            after = line[isin_match.end():]
        else:
            # 3. No ISIN found — use last 5 price-like tokens from the line
            # Price-like tokens: contain a decimal point and are < 10 chars
            tokens = line.split()
            price_tokens = [
                t for t in tokens
                if "." in t and len(t) <= 12 and re.match(r"[\d,\.]+$", t)
            ]
            nums = []
            for t in price_tokens[-5:]:
                v = _clean_number(t)
                if v is not None and v > 0:
                    nums.append(v)
            return nums

    return _extract_numbers_after_isin(after)


def _validate_ohlcv(nums: list[float]) -> bool:
    """Return True if nums looks like valid HIGH/LOW/CLOSE/PREV/VOL data."""
    if len(nums) < 3:
        return False
    high, low, close = nums[0], nums[1], nums[2]
    if high <= 0 or low <= 0 or close <= 0:
        return False
    # HIGH >= LOW (allow tiny floating point issues)
    if high < low * 0.99:
        return False
    # CLOSE roughly between LOW and HIGH (with some tolerance for VWAP)
    if close < low * 0.95 or close > high * 1.05:
        return False
    return True


def _parse_ticker_from_text(safe: str, text: str) -> Optional[dict]:
    """
    Find the price row for `safe` in the extracted PDF text.
    Returns dict with keys: high, low, close, prev_close, volume, no_trade
    Returns None if the ticker is not found.
    """
    cfg = TICKERS[safe]
    candidate_lines = _find_ticker_lines(safe, text)

    if not candidate_lines:
        return None

    isin = cfg["isin"] or _discovered_isins.get(safe)

    for line in candidate_lines:
        nums = _parse_numbers_from_line(line, isin)

        if len(nums) == 0:
            continue

        if len(nums) == 1:
            # No-trade: single price shown with dash
            return {
                "high": nums[0], "low": nums[0],
                "close": nums[0], "prev_close": nums[0],
                "volume": 0, "no_trade": True,
            }

        if len(nums) >= 4 and _validate_ohlcv(nums):
            return {
                "high": nums[0], "low": nums[1],
                "close": nums[2], "prev_close": nums[3],
                "volume": int(nums[4]) if len(nums) >= 5 else 0,
                "no_trade": False,
            }

        if len(nums) in (2, 3):
            # Ambiguous — treat as no-trade with the largest number as price
            price = max(nums)
            return {
                "high": price, "low": price,
                "close": price, "prev_close": price,
                "volume": 0, "no_trade": True,
            }

    return None


# ── CSV helpers ───────────────────────────────────────────────────────────────

ALL_COLS = ["Open", "High", "Low", "Close", "Volume", "Is_Stale"]


def _load_csv(safe: str) -> Optional[pd.DataFrame]:
    path = DATA_ROOT / f"{safe}_cleaned.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    df.index = pd.to_datetime(df.index)
    return df


def _save_csv(safe: str, df: pd.DataFrame) -> None:
    path = DATA_ROOT / f"{safe}_cleaned.csv"
    df = df.sort_index()
    df.index.name = "Date"
    df.to_csv(path)


def _merge_rows(
    existing: Optional[pd.DataFrame],
    new_rows: pd.DataFrame,
) -> pd.DataFrame:
    """
    Merge new price rows into existing data.
    New real trades (Is_Stale=0) overwrite stale rows for the same dates.
    New no-trade rows (Is_Stale=1) fill missing dates but don't overwrite existing real data.
    """
    if existing is None or existing.empty:
        return new_rows.sort_index()

    existing_other = existing[~existing.index.isin(new_rows.index)]
    # For overlapping dates: prefer real data from either source
    overlap_existing = existing[existing.index.isin(new_rows.index)]
    overlap_new = new_rows

    merged_overlap = pd.concat([overlap_existing, overlap_new])
    # Where both exist, prefer Is_Stale=0 (real trade)
    merged_overlap = merged_overlap.sort_values("Is_Stale")
    merged_overlap = merged_overlap[~merged_overlap.index.duplicated(keep="first")]

    combined = pd.concat([existing_other, merged_overlap]).sort_index()
    return combined[~combined.index.duplicated(keep="last")]


# ── Firestore update ──────────────────────────────────────────────────────────

_fb_app: Optional[firebase_admin.App] = None
_db = None


def _get_firestore_client():
    global _fb_app, _db
    if _db is not None:
        return _db

    sa_raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not sa_raw:
        return None

    if sa_raw.strip().startswith("{"):
        sa_dict = json.loads(sa_raw)
    else:
        with open(sa_raw, encoding="utf-8") as fh:
            sa_dict = json.load(fh)

    cred = fb_credentials.Certificate(sa_dict)
    _fb_app = firebase_admin.initialize_app(cred, {
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
    })
    _db = fb_firestore.client()
    return _db


def _update_firestore(
    _token: str,  # kept for signature compat; ignored — we use service account
    short_ticker: str,
    df: pd.DataFrame,
    dry_run: bool = False,
) -> None:
    """Update Firestore with latest price and price_preview array."""
    real = df[df["Is_Stale"] == 0]
    if real.empty:
        return

    last = real.iloc[-1]
    last_date = real.index[-1]
    prev = real.iloc[-2] if len(real) >= 2 else last
    change_pct = ((last["Close"] - prev["Close"]) / prev["Close"]) * 100 if prev["Close"] else 0
    preview = real["Close"].tail(30).tolist()

    if dry_run:
        print(f"    [DRY RUN] {short_ticker}: close={last['Close']}, date={last_date.date()}")
        return

    db = _get_firestore_client()
    if db is None:
        print("    Firestore skipped: FIREBASE_SERVICE_ACCOUNT_JSON env var not set")
        return

    db.collection("companies").document(short_ticker).update({
        "current_price": float(last["Close"]),
        "price_preview": [float(p) for p in preview],
        "price_date": last_date.strftime("%Y-%m-%d"),
        "last_updated": pd.Timestamp.now("UTC").isoformat(),
        "change_pct_today": float(change_pct),
    })
    print(f"    Firestore updated: {short_ticker} close={last['Close']}, date={last_date.date()}")


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape NSE daily price PDFs")
    parser.add_argument("--start", default="2025-10-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--tickers", nargs="*", help="Specific safe tickers (e.g. SCOM_NR)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-firestore", action="store_true")
    parser.add_argument("--skip-cache", action="store_true", help="Re-download even if cached")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today()

    target_safes = (
        [t.upper() for t in args.tickers if t.upper() in TICKERS]
        if args.tickers
        else list(TICKERS.keys())
    )

    days = _trading_days(start, end)
    print(f"Processing {len(days)} trading days from {start} to {end}")
    print(f"Tickers: {target_safes}")
    print(f"PDF cache: {PDF_CACHE_DIR}")
    print()

    session = requests.Session()
    session.headers.update(HEADERS)

    # Accumulate new price rows per ticker
    new_rows: dict[str, list[dict]] = {s: [] for s in target_safes}
    skipped = 0
    parsed = 0
    failed = 0

    for d in days:
        # Check if any target ticker is listed on this date
        active = [
            s for s in target_safes
            if TICKERS[s]["listed_from"] is None
            or d >= date.fromisoformat(TICKERS[s]["listed_from"])
        ]
        if not active:
            continue

        if args.skip_cache and _pdf_cache_path(d).exists():
            _pdf_cache_path(d).unlink()

        was_cached = _pdf_cache_path(d).exists()
        pdf_data = _download_pdf(d, session)
        if pdf_data is None:
            skipped += 1
            continue

        # Rate-limit only for fresh downloads; cached PDFs skip the delay
        if not was_cached:
            time.sleep(0.3)

        is_text = _is_text_pdf(pdf_data)
        method = "text" if is_text else "ocr"

        try:
            text = _get_pdf_text(pdf_data)
        except Exception as e:
            print(f"  [{d}] text extraction failed ({method}): {e}")
            failed += 1
            continue

        found_any = False
        for safe in active:
            result = _parse_ticker_from_text(safe, text)
            if result is None:
                continue
            found_any = True
            new_rows[safe].append({
                "Date": pd.Timestamp(d),
                "Open": result["prev_close"] if not result["no_trade"] else result["close"],
                "High": result["high"],
                "Low": result["low"],
                "Close": result["close"],
                "Volume": result["volume"],
                "Is_Stale": 1 if result["no_trade"] else 0,
            })

        if found_any:
            parsed += 1
            print(
                f"  [{d}] {method:4s} | "
                + " ".join(
                    f"{s.split('_')[0]}={new_rows[s][-1]['Close']:.2f}"
                    for s in active
                    if new_rows[s] and new_rows[s][-1]["Date"] == pd.Timestamp(d)
                )
            )
        else:
            print(f"  [{d}] {method:4s} | no data found")
            failed += 1

    print(f"\n=== Extraction complete: {parsed} parsed, {skipped} skipped (holiday/404), {failed} failed ===\n")

    # ── Update CSVs ────────────────────────────────────────────────────────────
    for safe in target_safes:
        rows = new_rows[safe]
        if not rows:
            print(f"[{safe}] No new rows extracted — skipping")
            continue

        new_df = pd.DataFrame(rows).set_index("Date")
        new_df.index = pd.to_datetime(new_df.index)
        new_df["Is_Stale"] = new_df["Is_Stale"].astype(int)

        existing = _load_csv(safe)
        rows_before = len(existing) if existing is not None else 0

        merged = _merge_rows(existing, new_df)
        rows_after = len(merged)

        if not args.dry_run:
            _save_csv(safe, merged)

        real_in_new = (new_df["Is_Stale"] == 0).sum()
        print(
            f"[{safe}] rows: {rows_before} -> {rows_after} "
            f"(+{rows_after - rows_before} new, {real_in_new} real trades extracted)"
        )

        if not args.skip_firestore:
            _update_firestore("", TICKERS[safe]["short"], merged, dry_run=args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
