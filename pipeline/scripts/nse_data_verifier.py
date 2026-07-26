"""
nse_data_verifier.py — Maker-checker for NSE daily price extraction.

Runs AFTER every scrape and produces a structured verification report. Catches:
  - Missing expected tickers (OCR phrase mismatches, company renames)
  - Unmatched data lines in the PDF (new companies / new OCR variants)
  - PREV_CLOSE mismatches (our CSV vs the PDF's reported previous close)
  - OHLC sanity violations

Usage:
  python pipeline/scripts/nse_data_verifier.py [--date YYYY-MM-DD] [--pdf /path/to.pdf]
  python pipeline/scripts/nse_data_verifier.py --rtdb-cross-check
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import sys
import tempfile
import os
from pathlib import Path
from typing import Any

import pdfplumber
import pytesseract
import requests

# ---------------------------------------------------------------------------
# Repo root and path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

DATA_CLEANED = _REPO_ROOT / "data" / "cleaned"

# Tesseract binary for Windows
_TESSERACT_WIN = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_TESSERACT_WIN):
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_WIN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Import shared helpers from scrape_nse_pdf
# ---------------------------------------------------------------------------
from pipeline.scripts.scrape_nse_pdf import (  # noqa: E402
    build_pdf_url,
    download_pdf,
    extract_price_rows,
    _is_data_line,
    _match_line_ocr,
)

# ---------------------------------------------------------------------------
# Active-ticker discovery
# ---------------------------------------------------------------------------

LOOKBACK_DAYS = 30


def get_active_tickers(data_dir: Path) -> set[str]:
    """
    Return the set of tickers that had at least one Volume > 0 row in the
    last LOOKBACK_DAYS calendar days.  A ticker whose CSV exists but has been
    completely quiet for 30+ days is considered inactive and omitted from the
    expected-daily set (avoids false MISSING alerts for suspended stocks).
    """
    import pandas as pd

    cutoff = (datetime.date.today() - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    active: set[str] = set()

    for csv_path in data_dir.glob("*_NR_cleaned.csv"):
        ticker = csv_path.stem.replace("_NR_cleaned", "")
        try:
            df = pd.read_csv(
                csv_path,
                usecols=["Date", "Volume", "Is_Stale"],
                dtype={"Is_Stale": int},
            )
            recent = df[(df["Date"] >= cutoff) & (df["Is_Stale"] == 0)]
            if (recent["Volume"] > 0).any():
                active.add(ticker)
        except Exception as exc:
            log.debug("get_active_tickers: skipping %s — %s", ticker, exc)

    return active


# ---------------------------------------------------------------------------
# OHLC sanity check
# ---------------------------------------------------------------------------

_OHLC_TOLERANCE = 0.01  # 1 % rounding allowance


def check_ohlc(ticker: str, fields: dict[str, Any]) -> list[str]:
    """Return list of violation descriptions, empty if clean."""
    violations: list[str] = []
    high = fields.get("high", 0.0)
    low  = fields.get("low",  0.0)
    close = fields.get("close", 0.0)
    volume = fields.get("volume", 0.0)

    if high < low:
        violations.append(f"High({high}) < Low({low})")
    if close < low * (1 - _OHLC_TOLERANCE):
        violations.append(f"Close({close}) < Low({low})")
    if close > high * (1 + _OHLC_TOLERANCE):
        violations.append(f"Close({close}) > High({high})")
    if volume <= 0:
        violations.append(f"Volume({volume}) <= 0")
    return violations


# ---------------------------------------------------------------------------
# Prev-close cross-check against CSV
# ---------------------------------------------------------------------------

PREV_CLOSE_THRESHOLD_PCT = 2.0  # flag if diff > 2 %


def _last_solid_close(ticker: str, before_date: datetime.date) -> float | None:
    """
    Return the most recent Is_Stale=0, Volume>0 close price for ticker
    strictly before before_date.  Returns None if not found.
    """
    import pandas as pd

    csv_path = DATA_CLEANED / f"{ticker}_NR_cleaned.csv"
    if not csv_path.exists():
        return None
    try:
        df = pd.read_csv(csv_path, parse_dates=["Date"])
        solid = df[(df["Is_Stale"] == 0) & (df["Volume"] > 0)]
        solid = solid[solid["Date"].dt.date < before_date]
        if solid.empty:
            return None
        return float(solid.sort_values("Date").iloc[-1]["Close"])
    except Exception:
        return None


def check_prev_close(
    ticker: str,
    pdf_prev: float,
    target_date: datetime.date,
) -> dict[str, Any] | None:
    """
    Compare PDF's reported prev_close against our CSV's last solid close.
    Returns a mismatch dict if difference > threshold, else None.
    """
    csv_last = _last_solid_close(ticker, target_date)
    if csv_last is None or csv_last <= 0 or pdf_prev <= 0:
        return None

    pct_diff = abs(pdf_prev - csv_last) / csv_last * 100
    if pct_diff > PREV_CLOSE_THRESHOLD_PCT:
        return {
            "ticker":   ticker,
            "pdf_prev": round(pdf_prev, 4),
            "csv_last": round(csv_last, 4),
            "pct_diff": round(pct_diff, 2),
        }
    return None


# ---------------------------------------------------------------------------
# Unmatched-line scanner (re-run OCR on PDF to collect raw lines)
# ---------------------------------------------------------------------------

def _scan_unmatched_lines(pdf_bytes: bytes, resolution: int = 250) -> list[str]:
    """
    Re-run OCR and collect raw text from lines that _is_data_line() accepts
    but _match_line_ocr() cannot identify.  These are potential new companies
    or new OCR variants that would silently drop data.
    """
    unmatched: list[str] = []
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    try:
        os.write(tmp_fd, pdf_bytes)
        os.close(tmp_fd)

        with pdfplumber.open(tmp_path) as pdf:
            # First try table mode; if tables found, no OCR lines to scan
            table_rows_found = 0
            for page in pdf.pages:
                for table in page.extract_tables():
                    table_rows_found += len([r for r in table if r and len(r) >= 9])
            if table_rows_found > 0:
                return []  # Table-mode PDF — no OCR lines to scan

            for page in pdf.pages:
                img = page.to_image(resolution=resolution).original
                text = pytesseract.image_to_string(img, config="--psm 6 --oem 3")
                for line in text.split("\n"):
                    line = line.strip()
                    if not line or not _is_data_line(line):
                        continue
                    ticker = _match_line_ocr(line)
                    if ticker is None:
                        unmatched.append(line[:120])
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return unmatched


# ---------------------------------------------------------------------------
# RTDB cross-check (optional)
# ---------------------------------------------------------------------------

def _rtdb_cross_check(date_str: str) -> dict[str, Any]:
    """
    Compare Is_Stale=0 CSV closes against RTDB values for date_str.
    Returns {ticker: {csv_close, rtdb_close, pct_diff}} for large mismatches.
    """
    import pandas as pd

    try:
        from pipeline.scripts.firebase_rtdb import get_price_node
        from pipeline.scripts.firebase_client import get_rtdb
        root_ref = get_rtdb()
    except Exception as exc:
        log.error("RTDB cross-check: Firebase init failed — %s", exc)
        return {}

    mismatches: dict[str, Any] = {}
    for csv_path in DATA_CLEANED.glob("*_NR_cleaned.csv"):
        ticker = csv_path.stem.replace("_NR_cleaned", "")
        try:
            df = pd.read_csv(csv_path, parse_dates=["Date"])
            row = df[
                (df["Date"].dt.date.astype(str) == date_str) &
                (df["Is_Stale"] == 0) &
                (df["Volume"] > 0)
            ]
            if row.empty:
                continue
            csv_close = float(row.iloc[0]["Close"])
            node = get_price_node(root_ref, ticker, date_str)
            if not node:
                mismatches[ticker] = {"csv_close": csv_close, "rtdb_close": None, "pct_diff": None}
                continue
            rtdb_close = float(node.get("c", 0))
            if rtdb_close <= 0:
                continue
            pct_diff = abs(csv_close - rtdb_close) / rtdb_close * 100
            if pct_diff > PREV_CLOSE_THRESHOLD_PCT:
                mismatches[ticker] = {
                    "csv_close":  round(csv_close, 4),
                    "rtdb_close": round(rtdb_close, 4),
                    "pct_diff":   round(pct_diff, 2),
                }
        except Exception as exc:
            log.debug("RTDB cross-check: error for %s — %s", ticker, exc)

    return mismatches


# ---------------------------------------------------------------------------
# Main verification logic
# ---------------------------------------------------------------------------

def verify(
    target_date: datetime.date,
    pdf_bytes: bytes,
    resolution: int = 250,
) -> dict[str, Any]:
    """
    Run all verification checks against the PDF for target_date.
    Returns the report dict.
    """
    date_str = target_date.isoformat()
    log.info("=== NSE Data Verifier: %s ===", date_str)

    # --- Step 1: Extract prices from PDF ---
    rows: list[tuple[str, dict]] = extract_price_rows(pdf_bytes, resolution=resolution)
    extracted_tickers: dict[str, dict] = {}
    for name_or_ticker, fields in rows:
        ticker = name_or_ticker if len(name_or_ticker) <= 6 else name_or_ticker
        extracted_tickers[ticker] = fields

    log.info("Extracted %d tickers from PDF", len(extracted_tickers))

    # --- Step 2: Prev-close cross-check ---
    prev_close_mismatches: list[dict] = []
    for ticker, fields in extracted_tickers.items():
        mismatch = check_prev_close(ticker, fields.get("prev_close", 0.0), target_date)
        if mismatch:
            prev_close_mismatches.append(mismatch)
            log.warning(
                "PREV_CLOSE_MISMATCH %s: PDF_prev=%.4f CSV_last=%.4f pct_diff=%.2f%%",
                mismatch["ticker"], mismatch["pdf_prev"], mismatch["csv_last"], mismatch["pct_diff"],
            )

    # --- Step 3: Missing tickers ---
    active_tickers = get_active_tickers(DATA_CLEANED)
    missing = sorted(active_tickers - set(extracted_tickers))
    for t in missing:
        log.warning("MISSING ticker: %s (was active in last %d days)", t, LOOKBACK_DAYS)

    # --- Step 4: Unmatched OCR lines ---
    log.info("Scanning for unmatched OCR lines …")
    unmatched_lines = _scan_unmatched_lines(pdf_bytes, resolution=resolution)
    for line in unmatched_lines:
        log.warning("UNMATCHED_LINE: %s", line)

    # --- Step 5: OHLC sanity ---
    ohlc_invalid: list[dict] = []
    for ticker, fields in extracted_tickers.items():
        violations = check_ohlc(ticker, fields)
        if violations:
            ohlc_invalid.append({"ticker": ticker, "violations": violations, "fields": fields})
            log.warning("OHLC_INVALID %s: %s", ticker, "; ".join(violations))

    # --- Step 6: Determine status ---
    if missing or ohlc_invalid:
        status = "FAIL"
    elif prev_close_mismatches or unmatched_lines:
        status = "WARN"
    else:
        status = "OK"

    report: dict[str, Any] = {
        "date":                  date_str,
        "extracted_count":       len(extracted_tickers),
        "missing":               missing,
        "prev_close_mismatches": prev_close_mismatches,
        "unmatched_lines":       unmatched_lines,
        "ohlc_invalid":          ohlc_invalid,
        "status":                status,
    }

    return report


def _print_summary(report: dict[str, Any]) -> None:
    log.info("=== Verification Summary: %s ===", report["date"])
    log.info("  Status           : %s", report["status"])
    log.info("  Extracted tickers: %d", report["extracted_count"])
    if report["missing"]:
        log.warning("  Missing tickers  : %s", report["missing"])
    else:
        log.info("  Missing tickers  : none")
    if report["prev_close_mismatches"]:
        log.warning("  Prev-close issues: %d", len(report["prev_close_mismatches"]))
        for m in report["prev_close_mismatches"]:
            log.warning(
                "    %s: PDF=%.4f CSV=%.4f  diff=%.2f%%",
                m["ticker"], m["pdf_prev"], m["csv_last"], m["pct_diff"],
            )
    else:
        log.info("  Prev-close issues: none")
    if report["unmatched_lines"]:
        log.warning("  Unmatched lines  : %d", len(report["unmatched_lines"]))
    else:
        log.info("  Unmatched lines  : none")
    if report["ohlc_invalid"]:
        log.warning("  OHLC violations  : %d", len(report["ohlc_invalid"]))
        for item in report["ohlc_invalid"]:
            log.warning("    %s: %s", item["ticker"], "; ".join(item["violations"]))
    else:
        log.info("  OHLC violations  : none")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="NSE maker-checker: verify today's PDF extraction against CSV history",
    )
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--pdf",  help="Local PDF path (skip download)")
    parser.add_argument(
        "--resolution",
        type=int,
        default=250,
        help="OCR resolution in DPI (default: 250)",
    )
    parser.add_argument(
        "--rtdb-cross-check",
        action="store_true",
        help="Also compare CSV closes vs RTDB for the target date",
    )
    args = parser.parse_args()

    target_date = (
        datetime.date.fromisoformat(args.date)
        if args.date
        else datetime.date.today()
    )

    # Gracefully handle weekends — no PDF exists
    if not args.date and target_date.weekday() >= 5:
        log.info(
            "NSE closed today (%s, %s). Nothing to verify.",
            target_date.isoformat(),
            target_date.strftime("%A"),
        )
        sys.exit(0)

    # --- Obtain PDF bytes ---
    if args.pdf:
        pdf_bytes = Path(args.pdf).read_bytes()
        log.info("Using local PDF: %s", args.pdf)
    else:
        url = build_pdf_url(target_date)
        log.info("Downloading PDF: %s", url)
        try:
            pdf_bytes = download_pdf(url)
        except requests.HTTPError as exc:
            log.error("PDF not available: %s", exc)
            # Not a fatal error in CI — report with empty extraction
            report: dict[str, Any] = {
                "date":                  target_date.isoformat(),
                "extracted_count":       0,
                "missing":               [],
                "prev_close_mismatches": [],
                "unmatched_lines":       [],
                "ohlc_invalid":          [],
                "status":                "WARN",
                "error":                 str(exc),
            }
            report_path = Path(f"/tmp/nse_verify_{target_date.isoformat()}.json")
            report_path.write_text(json.dumps(report, indent=2))
            log.info("Report written: %s", report_path)
            sys.exit(0)

    # --- Run verification ---
    report = verify(target_date, pdf_bytes, resolution=args.resolution)

    # --- Optional RTDB cross-check ---
    if args.rtdb_cross_check:
        log.info("Running RTDB cross-check …")
        rtdb_mismatches = _rtdb_cross_check(target_date.isoformat())
        report["rtdb_mismatches"] = rtdb_mismatches
        if rtdb_mismatches:
            log.warning("RTDB mismatches: %d tickers differ from CSV", len(rtdb_mismatches))
            if report["status"] == "OK":
                report["status"] = "WARN"

    # --- Print human-readable summary ---
    _print_summary(report)

    # --- Write JSON report ---
    report_path = Path(f"/tmp/nse_verify_{target_date.isoformat()}.json")
    report_path.write_text(json.dumps(report, indent=2))
    log.info("Report written: %s", report_path)


if __name__ == "__main__":
    main()
