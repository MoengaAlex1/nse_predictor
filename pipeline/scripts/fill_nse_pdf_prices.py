"""
fill_nse_pdf_prices.py

Downloads the NSE daily market bulletin PDFs and backfills missing closing
prices in Firebase Storage for the specified dates.

The NSE publishes a PDF for each trading day at:
    https://www.nse.co.ke/wp-content/uploads/DD-MON-YY.pdf

The bulletin lists every traded security with OHLCV data.

Usage:
    pip install pdfplumber                        # always needed
    pip install pdf2image pytesseract            # needed only if PDF is image-based
    # Tesseract binary: sudo apt-get install tesseract-ocr  (Linux/GHA)
    #                   brew install tesseract               (macOS)
    #                   winget install UB-Mannheim.TesseractOCR (Windows)

    python pipeline/scripts/fill_nse_pdf_prices.py --dates 2026-07-18 2026-07-21 2026-07-22
    python pipeline/scripts/fill_nse_pdf_prices.py --dates 2026-07-18 --dry-run

Env vars: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import argparse
import io
import logging
import re
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.push_to_firestore import (
    get_db,
    download_model_from_storage,
    upload_model_to_storage,
)
from config import load_companies

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_NSE_PDF_BASE = "https://www.nse.co.ke/wp-content/uploads/{date_str}.pdf"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Referer": "https://www.nse.co.ke/",
}

CSVS_TMP = Path(tempfile.gettempdir()) / "nse_pdf_csvs"

# Columns expected in the NSE daily bulletin (exact names vary by report version)
_HEADER_CLOSE_KEYWORDS = {"last", "close", "traded", "trade", "ltp"}
_HEADER_OPEN_KEYWORDS  = {"open"}
_HEADER_HIGH_KEYWORDS  = {"high"}
_HEADER_LOW_KEYWORDS   = {"low"}
_HEADER_VOL_KEYWORDS   = {"volume", "vol", "shares"}
_HEADER_CODE_KEYWORDS  = {"code", "security", "ticker", "symbol"}

# Number pattern: optional leading minus, digits with optional commas, decimal
_NUM_RE = re.compile(r"-?[\d,]+\.[\d]+|-?[\d,]{4,}")


def _date_to_pdf_name(d: date) -> str:
    """2026-07-18  →  '18-JUL-26'"""
    return d.strftime("%d-%b-%y").upper()


def _date_to_url(d: date) -> str:
    return _NSE_PDF_BASE.format(date_str=_date_to_pdf_name(d))


# ── PDF download ──────────────────────────────────────────────────────────────

def _download_pdf(url: str) -> bytes | None:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=60)
        if resp.status_code != 200:
            log.warning("PDF download HTTP %d: %s", resp.status_code, url)
            return None
        if not resp.content.startswith(b"%PDF"):
            log.warning("Response from %s is not a PDF (got: %r)", url, resp.content[:20])
            return None
        log.info("Downloaded %d KB from %s", len(resp.content) // 1024, url)
        return resp.content
    except Exception as exc:
        log.error("Failed to download %s: %s", url, exc)
        return None


# ── Price parsing helpers ─────────────────────────────────────────────────────

def _clean_num(s: str) -> float | None:
    try:
        return float(s.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _find_col(header_cells: list[str], keywords: set[str]) -> int | None:
    """Return index of the first header cell whose lower text contains any keyword."""
    for i, cell in enumerate(header_cells):
        lc = cell.lower()
        if any(kw in lc for kw in keywords):
            return i
    return None


def _parse_table(rows: list[list[str | None]], valid_tickers: set[str]) -> dict[str, dict]:
    """Parse a list-of-list table (as returned by pdfplumber) into {ticker: OHLCV}."""
    if not rows:
        return {}

    # Find the header row — the one that mentions "code" or "security"
    header_idx = None
    for i, row in enumerate(rows[:6]):
        cells = [str(c or "").strip() for c in row]
        if any(any(kw in c.lower() for kw in _HEADER_CODE_KEYWORDS) for c in cells):
            header_idx = i
            break

    if header_idx is None:
        # Fallback: treat row 0 as header
        header_idx = 0

    header = [str(c or "").strip() for c in rows[header_idx]]
    col_code  = _find_col(header, _HEADER_CODE_KEYWORDS) or 0
    col_close = _find_col(header, _HEADER_CLOSE_KEYWORDS)
    col_open  = _find_col(header, _HEADER_OPEN_KEYWORDS)
    col_high  = _find_col(header, _HEADER_HIGH_KEYWORDS)
    col_low   = _find_col(header, _HEADER_LOW_KEYWORDS)
    col_vol   = _find_col(header, _HEADER_VOL_KEYWORDS)

    if col_close is None:
        log.debug("Could not identify closing-price column in header: %s", header)
        return {}

    results: dict[str, dict] = {}
    for row in rows[header_idx + 1:]:
        if not row or len(row) <= col_close:
            continue
        cells = [str(c or "").strip() for c in row]
        code = cells[col_code].upper().strip()
        if not code or code not in valid_tickers:
            continue

        close = _clean_num(cells[col_close])
        if close is None or close <= 0:
            continue

        ohlcv: dict = {"Close": close, "Open": close, "High": close, "Low": close, "Volume": 0}
        if col_open  is not None and col_open  < len(cells): ohlcv["Open"]   = _clean_num(cells[col_open])  or close
        if col_high  is not None and col_high  < len(cells): ohlcv["High"]   = _clean_num(cells[col_high])  or close
        if col_low   is not None and col_low   < len(cells): ohlcv["Low"]    = _clean_num(cells[col_low])   or close
        if col_vol   is not None and col_vol   < len(cells): ohlcv["Volume"] = int(_clean_num(cells[col_vol]) or 0)

        results[code] = ohlcv
    return results


def _parse_text(text: str, valid_tickers: set[str]) -> dict[str, dict]:
    """
    Regex-based fallback parser for raw extracted or OCR'd text.

    NSE daily bulletin line format (approximate):
        CODE   Company Name   prev_close   open   high   low   close   volume   value

    Strategy: for each line, look for a valid ticker in the first ~20 chars,
    then collect all numbers on the rest of the line. The 5th number is
    typically the closing price (prev_close, open, high, low, CLOSE, volume).
    """
    results: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Ticker must appear early in the line
        parts = line.split()
        if not parts:
            continue
        # The code might be the 1st or 2nd token (some formats prefix with a number)
        code = None
        for token in parts[:3]:
            upper = re.sub(r"[^A-Z&]", "", token.upper())
            if upper in valid_tickers:
                code = upper
                break
        if not code:
            continue

        nums = [_clean_num(m) for m in _NUM_RE.findall(line)]
        nums = [n for n in nums if n is not None and n > 0]
        if len(nums) < 5:
            continue

        # Positions: 0=prev_close, 1=open, 2=high, 3=low, 4=close, 5+=volume/value
        close  = nums[4]
        open_  = nums[1]
        high   = nums[2]
        low    = nums[3]
        volume = int(nums[5]) if len(nums) > 5 else 0

        if close <= 0:
            continue

        results[code] = {
            "Close": close, "Open": open_, "High": high, "Low": low, "Volume": volume,
        }
    return results


# ── Extraction strategies ─────────────────────────────────────────────────────

def _extract_via_pdfplumber(pdf_bytes: bytes, valid_tickers: set[str]) -> dict[str, dict]:
    try:
        import pdfplumber
    except ImportError:
        log.warning("pdfplumber not installed — run: pip install pdfplumber")
        return {}

    try:
        results: dict[str, dict] = {}
        raw_text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                # Try table extraction first
                tables = page.extract_tables()
                for table in tables:
                    parsed = _parse_table(table, valid_tickers)
                    results.update(parsed)
                # Also accumulate raw text for fallback
                raw_text += (page.extract_text() or "") + "\n"

        if results:
            log.info("pdfplumber table extraction: found %d tickers", len(results))
            return results

        # Table extraction found nothing — try raw text
        if raw_text.strip():
            results = _parse_text(raw_text, valid_tickers)
            if results:
                log.info("pdfplumber text fallback: found %d tickers", len(results))
            return results
    except Exception as exc:
        log.warning("pdfplumber extraction failed: %s", exc)

    return {}


def _extract_via_ocr(pdf_bytes: bytes, valid_tickers: set[str]) -> dict[str, dict]:
    """Convert PDF pages to images and OCR them."""
    try:
        from pdf2image import convert_from_bytes
    except ImportError:
        log.warning("pdf2image not installed — run: pip install pdf2image")
        return {}
    try:
        import pytesseract
    except ImportError:
        log.warning("pytesseract not installed — run: pip install pytesseract")
        return {}

    try:
        images = convert_from_bytes(pdf_bytes, dpi=300)
    except Exception as exc:
        log.warning("pdf2image conversion failed: %s", exc)
        return {}

    full_text = ""
    for i, img in enumerate(images):
        try:
            # Use PSM 6 (uniform block of text) for tabular data
            text = pytesseract.image_to_string(img, config="--psm 6")
            full_text += text + "\n"
        except Exception as exc:
            log.warning("OCR failed on page %d: %s", i + 1, exc)

    if not full_text.strip():
        return {}

    results = _parse_text(full_text, valid_tickers)
    log.info("OCR extraction: found %d tickers", len(results))
    return results


def extract_prices(pdf_bytes: bytes, valid_tickers: set[str]) -> dict[str, dict]:
    """
    Try extraction strategies in order; return the best result.
    Result: {TICKER_BASE: {"Close": float, "Open": float, "High": float, "Low": float, "Volume": int}}
    """
    result = _extract_via_pdfplumber(pdf_bytes, valid_tickers)
    if len(result) >= 5:
        return result

    log.info("pdfplumber found %d tickers — trying OCR", len(result))
    ocr_result = _extract_via_ocr(pdf_bytes, valid_tickers)
    if len(ocr_result) > len(result):
        result = ocr_result

    if not result:
        log.warning("No prices extracted from PDF — all strategies returned empty")
    return result


# ── Firebase backfill ─────────────────────────────────────────────────────────

def _load_local_csv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            return None
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=False, format="mixed")
        df = df.set_index(date_col).sort_index()
        df.index.name = "Date"
        return df
    except Exception as exc:
        log.warning("Could not load %s: %s", path, exc)
        return None


def _safe_name(ticker: str) -> str:
    return ticker.replace(".", "_")


def backfill_date(
    trade_date: date,
    prices: dict[str, dict],
    companies: list[dict],
    dry_run: bool = False,
) -> dict[str, bool]:
    """
    For each company that has a price in `prices`, inject a row for `trade_date`
    into its Firebase Storage CSV.

    Returns {safe_ticker: updated (True) | already_had_data (False)}
    """
    CSVS_TMP.mkdir(parents=True, exist_ok=True)
    ts = pd.Timestamp(trade_date)
    results: dict[str, bool] = {}

    for company in companies:
        ticker = company["ticker"]
        safe   = _safe_name(ticker)
        base   = safe[:-3] if safe.endswith("_NR") else safe

        ohlcv = prices.get(base)
        if not ohlcv:
            log.debug("%s: no price found in PDF for ticker base %s", safe, base)
            results[safe] = False
            continue

        storage_path = f"data/cleaned/{safe}_cleaned.csv"
        local_path   = CSVS_TMP / f"{safe}_cleaned.csv"

        # Download existing CSV
        in_storage = download_model_from_storage(storage_path, str(local_path))

        existing_df: pd.DataFrame | None = None
        if local_path.exists():
            existing_df = _load_local_csv(local_path)
            if existing_df is not None and "Is_Stale" in existing_df.columns:
                existing_df = existing_df[existing_df["Is_Stale"] != 1]

        # Check if this date already has real data
        if existing_df is not None and ts in existing_df.index:
            row = existing_df.loc[ts]
            if hasattr(row, "Volume") and float(getattr(row, "Volume", 0)) > 0:
                log.info("%s: %s already has data (close=%.4f) — skipping",
                         safe, trade_date, float(row["Close"]))
                results[safe] = False
                continue
            # Row exists but Volume=0 (synthetic/stale) — overwrite it
            existing_df = existing_df.drop(index=ts)

        # Build the new row
        new_row = pd.DataFrame(
            [{k: ohlcv[k] for k in ("Open", "High", "Low", "Close", "Volume") if k in ohlcv}],
            index=pd.DatetimeIndex([ts], name="Date"),
        )

        if dry_run:
            log.info("[DRY-RUN] %s  %s  close=%.4f  volume=%d",
                     safe, trade_date, ohlcv["Close"], ohlcv.get("Volume", 0))
            results[safe] = True
            continue

        if existing_df is not None and not existing_df.empty:
            keep_cols = [c for c in new_row.columns if c in existing_df.columns]
            existing_sub = existing_df[[c for c in keep_cols if c in existing_df.columns]]
            combined = pd.concat([existing_sub, new_row[keep_cols]]).sort_index()
        else:
            combined = new_row.sort_index()

        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined[combined.index.dayofweek < 5]  # weekdays only

        combined.to_csv(local_path)
        upload_model_to_storage(str(local_path), storage_path)

        log.info("%s  %s  close=%.4f  volume=%d  → uploaded",
                 safe, trade_date, ohlcv["Close"], ohlcv.get("Volume", 0))
        results[safe] = True

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill NSE prices from daily bulletin PDFs")
    parser.add_argument(
        "--dates", nargs="+", required=True,
        help="Trading dates to fill, YYYY-MM-DD (e.g. 2026-07-18 2026-07-21 2026-07-22)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be written without touching Firebase",
    )
    parser.add_argument(
        "--save-pdf", action="store_true",
        help="Save downloaded PDFs to pipeline/data/daily_pdfs/",
    )
    args = parser.parse_args()

    if not args.dry_run:
        get_db()

    companies   = load_companies()
    valid_tickers = {
        (s[:-3] if s.endswith("_NR") else s)
        for s in (_safe_name(c["ticker"]) for c in companies)
    }
    log.info("Tracking %d ticker bases", len(valid_tickers))

    pdf_dir: Path | None = None
    if args.save_pdf:
        pdf_dir = PIPELINE_ROOT / "data" / "daily_pdfs"
        pdf_dir.mkdir(parents=True, exist_ok=True)

    total_updated = 0
    for date_str in args.dates:
        try:
            trade_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            log.error("Invalid date format: %s (expected YYYY-MM-DD)", date_str)
            continue

        if trade_date.weekday() >= 5:
            log.warning("Skipping %s — it's a weekend", trade_date)
            continue

        url = _date_to_url(trade_date)
        log.info("=== Processing %s (%s) ===", trade_date, url)

        pdf_bytes = _download_pdf(url)
        if pdf_bytes is None:
            log.error("Could not download PDF for %s — skipping", trade_date)
            continue

        if pdf_dir is not None:
            pdf_name = f"{_date_to_pdf_name(trade_date)}.pdf"
            (pdf_dir / pdf_name).write_bytes(pdf_bytes)
            log.info("Saved PDF → %s", pdf_dir / pdf_name)

        prices = extract_prices(pdf_bytes, valid_tickers)
        if not prices:
            log.error("No prices extracted for %s", trade_date)
            continue

        log.info("Extracted %d prices for %s", len(prices), trade_date)

        updates = backfill_date(trade_date, prices, companies, dry_run=args.dry_run)
        n_updated = sum(1 for v in updates.values() if v)
        total_updated += n_updated
        log.info("%s: updated %d / %d companies", trade_date, n_updated, len(companies))

    log.info("=== Done: %d total company-dates updated ===", total_updated)


if __name__ == "__main__":
    main()
