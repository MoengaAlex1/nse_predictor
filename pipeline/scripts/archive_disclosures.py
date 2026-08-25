"""
Archive every NSE-published PDF into Firebase Storage and index the
extracted text into Firestore under ``disclosures/{ticker}/items/{sha}``.

This is milestone M2 of the data-mining expansion. It builds on
``refresh_nse_disclosures.py`` — that script catalogs URL + title into
``financials/{ticker}.announcements[]`` / ``.corporate_actions[]`` /
``.dividends[]`` (URL-only, no download). This script picks up from
there and:

  1. Enumerates every unique PDF URL referenced by any Firestore
     financials doc.
  2. Skips URLs already indexed (fast path — one query per URL).
  3. Downloads the PDF, hashes bytes, uploads to Storage at
     ``nse-pdfs/{ticker}/{yyyy-mm}/{sha16}.pdf``.
  4. Extracts text — native pdfplumber first, then pytesseract OCR at
     250 dpi if the native pass returned < 200 chars (scanned image).
  5. Writes ``disclosures/{ticker}/items/{sha16}`` with the metadata,
     the extracted text (capped at 900 KB inline), page count, and
     archival provenance.

Idempotent: a re-run of the script will skip URLs already indexed.
A ``--force`` flag re-downloads + re-extracts if you're iterating on
the OCR logic.

Usage
-----
    # Full backfill (all tickers, all URLs in Firestore financials)
    python pipeline/scripts/archive_disclosures.py

    # Targeted ticker(s)
    python pipeline/scripts/archive_disclosures.py --tickers BOC SCOM

    # Cap for testing
    python pipeline/scripts/archive_disclosures.py --limit 20 --dry-run

    # Force re-extract (useful after tuning OCR)
    python pipeline/scripts/archive_disclosures.py --tickers BOC --force

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
from __future__ import annotations

import argparse
import hashlib
import io
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

# Firestore doc-value size cap is 1 MiB. Leave headroom for other fields.
MAX_INLINE_TEXT_BYTES = 900_000
FIRST_PAGE_PREVIEW_CHARS = 500

# Tesseract's default is fast enough at 250 dpi and matches the resolution
# scrape_nse_pdf.py uses for the price-table PDFs. 300 dpi is only ~30%
# more accurate but takes ~2x wall-clock — not worth it for text bodies.
OCR_DPI = 250

# If native pdfplumber text extraction returns fewer than this many chars
# per page on average, treat the PDF as scanned and fall back to OCR.
NATIVE_MIN_CHARS_PER_PAGE = 100

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0",
    "Accept": "application/pdf,*/*",
}
HTTP_TIMEOUT = 60


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_native(pdf_bytes: bytes) -> tuple[str, int]:
    """Return (text, page_count) using pdfplumber's native extractor.

    Returns empty string if the PDF is a scanned image (no text layer)."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(f"[PAGE {i + 1}]\n{text}")
    return "\n\n".join(parts), page_count


def _extract_ocr(pdf_bytes: bytes) -> tuple[str, int]:
    """Return (text, page_count) via pytesseract OCR at OCR_DPI.

    Uses PyMuPDF for rasterisation because it's ~5× faster than pdfplumber's
    ``page.to_image()`` on large scanned PDFs."""
    import fitz  # PyMuPDF
    import pytesseract
    from PIL import Image

    parts: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_count = doc.page_count
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=OCR_DPI)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img)
            if text.strip():
                parts.append(f"[PAGE {i + 1}]\n{text}")
    return "\n\n".join(parts), page_count


def extract_text(pdf_bytes: bytes) -> tuple[str, int, str]:
    """Return (text, page_count, method) — method ∈ {"native","ocr","hybrid","failed"}."""
    try:
        native_text, page_count = _extract_native(pdf_bytes)
    except Exception as exc:
        log.warning("native extract failed: %s", exc)
        native_text, page_count = "", 0

    # Detect scanned-image PDF: no text layer.
    density = len(native_text) / max(page_count, 1)
    if native_text and density >= NATIVE_MIN_CHARS_PER_PAGE:
        return native_text, page_count, "native"

    # Fallback to OCR.
    try:
        ocr_text, ocr_page_count = _extract_ocr(pdf_bytes)
    except Exception as exc:
        log.warning("OCR extract failed: %s", exc)
        if native_text:
            return native_text, page_count, "native"  # Better than nothing.
        return "", page_count, "failed"

    if native_text and ocr_text:
        # Hybrid: prefer OCR for content pages, keep any native cover-page text.
        return ocr_text, ocr_page_count or page_count, "hybrid"
    return ocr_text, ocr_page_count or page_count, "ocr"


# ---------------------------------------------------------------------------
# URL discovery
# ---------------------------------------------------------------------------

_URL_FIELDS = ("url", "source_url")


def _pluck_url(rec: dict) -> str | None:
    for f in _URL_FIELDS:
        v = rec.get(f)
        if isinstance(v, str) and v.lower().endswith(".pdf"):
            return v
    return None


def enumerate_urls(db, tickers: list[str] | None) -> list[dict]:
    """Yield {ticker, url, kind, date, title} for every PDF URL referenced
    by any financials doc. If ``tickers`` is given, restrict to those."""
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (ticker, url)

    if tickers:
        docs = (db.collection("financials").document(t).get() for t in tickers)
    else:
        docs = db.collection("financials").stream()

    for snap in docs:
        if not snap.exists:
            continue
        ticker = snap.id
        data = snap.to_dict() or {}
        for kind, key in (
            ("financial_result", "announcements"),
            ("corporate_action", "corporate_actions"),
            ("dividend", "dividends"),
        ):
            for rec in data.get(key, []) or []:
                if not isinstance(rec, dict):
                    continue
                url = _pluck_url(rec)
                if not url:
                    continue
                if (ticker, url) in seen:
                    continue
                seen.add((ticker, url))
                out.append({
                    "ticker": ticker,
                    "url":    url,
                    "kind":   rec.get("type") or kind,
                    "date":   rec.get("date") or rec.get("announcement_date"),
                    "title":  rec.get("title") or "",
                })
    return out


# ---------------------------------------------------------------------------
# Dedup + write
# ---------------------------------------------------------------------------

def _already_archived(db, ticker: str, source_url: str) -> str | None:
    """Return the existing doc id (sha16) if this URL has been archived
    for this ticker, else None. One query per URL."""
    q = (db.collection("disclosures").document(ticker).collection("items")
         .where("source_url", "==", source_url).limit(1))
    for snap in q.stream():
        return snap.id
    return None


def _upload_to_storage(bucket, storage_path: str, pdf_bytes: bytes) -> None:
    """Upload PDF to Firebase Storage — no-op if the blob is already there
    with the same size (idempotent)."""
    blob = bucket.blob(storage_path)
    if blob.exists():
        blob.reload()
        if blob.size == len(pdf_bytes):
            return
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")


def _write_disclosure(
    db, ticker: str, sha16: str, doc: dict, dry_run: bool,
) -> None:
    if dry_run:
        return
    ref = db.collection("disclosures").document(ticker).collection("items").document(sha16)
    ref.set(doc, merge=True)

    # Roll-up counter on the parent doc so the frontend can show "N items"
    # without a full collection scan.
    parent = db.collection("disclosures").document(ticker)
    parent.set({
        "ticker":              ticker,
        "latest_published_at": doc.get("published_at"),
        "updated_at":          datetime.now(timezone.utc).isoformat(),
        # NOTE: item_count is written by a separate roll-up pass, not here,
        # to avoid a read+increment race on parallel workers.
    }, merge=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process(job: dict, db, bucket, dry_run: bool, force: bool) -> str:
    """Process one URL. Returns one of: "skipped", "archived", "failed"."""
    ticker = job["ticker"]
    url = job["url"]

    if not force:
        existing = _already_archived(db, ticker, url)
        if existing:
            return "skipped"

    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        r.raise_for_status()
    except Exception as exc:
        log.warning("  [%s] download failed %s: %s", ticker, url, exc)
        return "failed"

    pdf_bytes = r.content
    if len(pdf_bytes) < 1024 or not pdf_bytes[:4] == b"%PDF":
        log.warning("  [%s] not a PDF (%d bytes): %s", ticker, len(pdf_bytes), url)
        return "failed"

    sha = hashlib.sha256(pdf_bytes).hexdigest()
    sha16 = sha[:16]

    text, page_count, method = extract_text(pdf_bytes)
    truncated = False
    text_bytes = text.encode("utf-8")
    if len(text_bytes) > MAX_INLINE_TEXT_BYTES:
        truncated = True
        text = text_bytes[:MAX_INLINE_TEXT_BYTES].decode("utf-8", errors="ignore")

    # Figure out the yyyy-mm bucket from the record date.
    published = job.get("date") or ""
    yyyy_mm = published[:7] if len(published) >= 7 else "unknown"
    storage_path = f"nse-pdfs/{ticker}/{yyyy_mm}/{sha16}.pdf"

    if not dry_run:
        _upload_to_storage(bucket, storage_path, pdf_bytes)

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "sha256":         sha,
        "sha16":          sha16,
        "ticker":         ticker,
        "source_url":     url,
        "title":          job.get("title") or "",
        "kind":           job.get("kind") or "other",
        "published_at":   published,
        "storage_path":   storage_path,
        "archived_at":    now,
        "size_bytes":     len(pdf_bytes),
        "page_count":     page_count,
        "extract_method": method,
        "extract_status": "success" if text else ("empty" if method != "failed" else "failed"),
        "text":           text,
        "text_length":    len(text),
        "text_truncated": truncated,
        "first_page_text": text[:FIRST_PAGE_PREVIEW_CHARS],
        "discovered_via": "archive_disclosures",
    }

    _write_disclosure(db, ticker, sha16, doc, dry_run)

    log.info(
        "  [%s] archived %s (%d pages, %s, %d chars%s)",
        ticker, sha16, page_count, method, len(text), " truncated" if truncated else "",
    )
    return "archived"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*",
                        help="Restrict to these ticker short codes (default: all)")
    parser.add_argument("--limit", type=int,
                        help="Cap on URLs to process (default: no cap)")
    parser.add_argument("--kinds", nargs="*",
                        help="Restrict to these kinds "
                             "(financial_result / corporate_action / dividend / …)")
    parser.add_argument("--force", action="store_true",
                        help="Re-download + re-extract even if already indexed")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip Storage upload and Firestore write")
    args = parser.parse_args()

    from pipeline.scripts.firebase_client import get_firestore  # noqa: E402
    from firebase_admin import storage as fb_storage             # noqa: E402

    db = get_firestore()
    bucket = fb_storage.bucket()
    log.info("Storage bucket: %s", bucket.name)

    jobs = enumerate_urls(db, args.tickers)
    if args.kinds:
        wanted = {k.lower() for k in args.kinds}
        jobs = [j for j in jobs if (j.get("kind") or "").lower() in wanted]
    if args.limit:
        jobs = jobs[:args.limit]

    log.info("URLs to consider: %d across %d tickers",
             len(jobs), len({j["ticker"] for j in jobs}))

    stats = {"skipped": 0, "archived": 0, "failed": 0}
    for i, job in enumerate(jobs, start=1):
        try:
            outcome = process(job, db, bucket, args.dry_run, args.force)
            stats[outcome] = stats.get(outcome, 0) + 1
        except Exception as exc:
            log.warning("  [%s] unhandled: %s", job.get("ticker"), exc)
            stats["failed"] = stats.get("failed", 0) + 1
        if i % 20 == 0:
            log.info("  progress %d/%d — archived=%d skipped=%d failed=%d",
                     i, len(jobs), stats.get("archived", 0),
                     stats.get("skipped", 0), stats.get("failed", 0))

    verb = "would have archived" if args.dry_run else "archived"
    log.info("=== Done ===")
    log.info("  %s: %d, skipped (already indexed): %d, failed: %d",
             verb, stats.get("archived", 0), stats.get("skipped", 0), stats.get("failed", 0))


if __name__ == "__main__":
    main()
