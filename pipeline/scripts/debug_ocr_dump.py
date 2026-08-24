"""
debug_ocr_dump.py — one-shot: download NSE PDF for a date, run OCR at 250 dpi
and 300 dpi, and dump the raw text + a per-line classification (data line?
matched? which ticker?) to stdout for inspection.

Usage:
    python pipeline/scripts/debug_ocr_dump.py --date 2026-08-21
"""
from __future__ import annotations

import argparse
import datetime
import sys
import tempfile
from pathlib import Path

import pdfplumber
import pytesseract

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.scripts.scrape_nse_pdf import (  # noqa: E402
    NSE_PHRASES,
    _NSE_PHRASES_SORTED,
    _is_data_line,
    _match_line_ocr,
    _parse_ocr_row,
    build_pdf_url,
    download_pdf,
)


def dump(pdf_bytes: bytes, resolution: int) -> None:
    print(f"\n\n======= OCR @ {resolution} dpi =======")
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        with open(tmp_path, "wb") as f:
            f.write(pdf_bytes)

        with pdfplumber.open(tmp_path) as pdf:
            for page_i, page in enumerate(pdf.pages):
                print(f"\n--- Page {page_i} ---")
                img = page.to_image(resolution=resolution).original
                text = pytesseract.image_to_string(img, config="--psm 6 --oem 3")
                for line_i, raw in enumerate(text.split("\n")):
                    line = raw.strip()
                    if not line:
                        continue
                    is_data = _is_data_line(line)
                    tag = "DATA " if is_data else "     "
                    if is_data:
                        t = _match_line_ocr(line)
                        if t is None:
                            tag = "UNMAT"
                        elif t in ("__ETF__", "__SKIP__"):
                            tag = f"{t[:5]}"
                        else:
                            parsed = _parse_ocr_row(line, t)
                            tag = f"OK:{t:<4}" if parsed else f"FAIL:{t}"
                    print(f"  [{tag}] {line}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    args = p.parse_args()
    target = datetime.date.fromisoformat(args.date)

    print(f"Downloading {build_pdf_url(target)}")
    pdf_bytes = download_pdf(build_pdf_url(target))
    print(f"Got {len(pdf_bytes):,} bytes")
    print(f"NSE_PHRASES has {len(NSE_PHRASES)} entries, {len(_NSE_PHRASES_SORTED)} sorted")

    dump(pdf_bytes, 250)
    dump(pdf_bytes, 300)


if __name__ == "__main__":
    main()
