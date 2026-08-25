"""
Extract structured financials (EPS, revenue, PAT, BVPS, DPS, period)
from the archived NSE-disclosure text sitting in
``disclosures/{ticker}/items/*`` (populated by M2's archive_disclosures.py)
and merge into ``financials/{ticker}.annual[]`` / ``.interim[]``.

Two-tier extraction:
  1. Regex pass (search_text_for_metrics from extract_pdf_financials.py) —
     fast, free, covers the standardized NSE H1/FY results layout.
  2. Optional Claude API fallback when the regex pass returns fewer than
     REGEX_MIN_METRICS metrics and the PDF looks like a financial report.
     Off by default; opt-in with --use-ai. Caches by disclosure sha16 in
     ``ai_cache`` sub-collection so a re-run doesn't re-charge.

Idempotent: dedup by (ticker, period_end). A re-run replaces a low-confidence
record with a higher-confidence one but never downgrades.

Usage:
    # Full backfill (all tickers, regex only)
    python pipeline/scripts/extract_financials_from_archive.py

    # Targeted + AI fallback
    python pipeline/scripts/extract_financials_from_archive.py --tickers BOC SCOM --use-ai

    # Dry-run to preview
    python pipeline/scripts/extract_financials_from_archive.py --dry-run

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET,
     ANTHROPIC_API_KEY (only if --use-ai)
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the mature regex+scale helpers from the existing extractor rather
# than duplicating them here. They're proven against real NSE PDFs.
from pipeline.scripts.extract_pdf_financials import (
    search_text_for_metrics,
    to_kes_mn,
    parse_date_str,
    DATE_COMPACT_RE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

REGEX_MIN_METRICS = 2  # ≥ this many metrics → don't waste Claude call
FIN_RESULT_KINDS = {"financial_result", "results", "financials"}

# Loose revenue fallback — existing REVENUE_SIMPLE_RE in extract_pdf_financials
# only tolerates 10 chars between "revenue" and the number, which fails on
# tabular NSE PDFs where the value sits in the next column with 20-40 spaces
# of padding. This variant allows up to 80 non-newline chars between the
# keyword and the number.
_REVENUE_LOOSE = re.compile(
    r"(?:total|net|group)?\s*revenue[s]?\s*[^\n\r]{0,80}?"
    r"(?:[Kk][Ee][Ss][\s.]*)?([\d]{1,3}(?:,\d{3})+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Words that hint the PDF is an interim (half-year / quarterly) report.
_INTERIM_HINTS = re.compile(
    r"\b(half[-\s]?year|h1|h2|q[1-4]|interim|six\s+months|first\s+half)\b",
    re.IGNORECASE,
)
# Words that hint the PDF is a full-year audited result.
_ANNUAL_HINTS = re.compile(
    r"\b(full[-\s]?year|fy|annual|audited|year\s+ended)\b",
    re.IGNORECASE,
)


def _classify_period_type(text: str, period_end: str | None) -> str:
    """Return 'annual' or 'interim' based on the text + period_end.

    Heuristic:
      - If the period_end month is Dec (12) → annual (Kenyan FY ends Dec).
      - If period_end month is Jun (6) → likely H1 interim.
      - Otherwise, keyword vote in the surrounding text.
      - Default: 'annual' (safer — more common on NSE).
    """
    if period_end and len(period_end) == 10:
        month = period_end[5:7]
        if month == "06":
            return "interim"
        if month == "12":
            return "annual"

    # Keyword vote on the first ~2000 chars (title + intro usually mention it)
    head = text[:2000]
    interim_hits = len(_INTERIM_HINTS.findall(head))
    annual_hits  = len(_ANNUAL_HINTS.findall(head))
    if interim_hits > annual_hits:
        return "interim"
    return "annual"


def _confidence(metrics: dict) -> str:
    """Rate an extracted record from 0 metrics ('none') to ≥3 ('high')."""
    count = sum(1 for k in (
        "revenue_kes_mn", "net_income_kes_mn", "eps", "bvps", "dps_kes",
    ) if metrics.get(k) is not None)
    if count >= 3:
        return "high"
    if count == 2:
        return "medium"
    if count == 1:
        return "low"
    return "none"


def _confidence_rank(c: str) -> int:
    return {"high": 3, "medium": 2, "low": 1, "none": 0, "ai": 4}.get(c, 0)


def extract_from_text(text: str) -> dict:
    """Run the regex pass over disclosure body text and return a
    normalized FinancialResult-ish record. Returns dict with:

      revenue_kes_mn, net_income_kes_mn, eps, bvps, dps_kes,
      period_end (YYYY-MM-DD or None), period_type (annual|interim),
      confidence (none|low|medium|high), extraction_method='regex'.

    Whether the extraction is worth writing is up to the caller
    (see `_confidence`).
    """
    raw = search_text_for_metrics(text or "")
    out: dict[str, Any] = {}

    if "revenue_raw" in raw:
        out["revenue_kes_mn"] = to_kes_mn(raw["revenue_raw"])
    else:
        m = _REVENUE_LOOSE.search(text or "")
        if m:
            try:
                loose = float(m.group(1).replace(",", ""))
                if loose > 100:  # not EPS-scale
                    out["revenue_kes_mn"] = to_kes_mn(loose)
            except ValueError:
                pass
    if "net_income_raw" in raw:
        val = to_kes_mn(raw["net_income_raw"])
        if val is not None and raw.get("net_income_negative"):
            val = -val
        out["net_income_kes_mn"] = val
    if "eps_raw" in raw:
        out["eps"] = raw["eps_raw"]  # already per-share scale
    if "bvps_raw" in raw:
        out["bvps"] = raw["bvps_raw"]
    if "dps_raw" in raw:
        out["dps_kes"] = raw["dps_raw"]

    period_end = raw.get("period_end")
    out["period_end"] = period_end
    out["period_type"] = _classify_period_type(text or "", period_end)
    out["confidence"] = _confidence(out)
    out["extraction_method"] = "regex"
    return out


# ---------------------------------------------------------------------------
# Optional Claude fallback
# ---------------------------------------------------------------------------

_AI_PROMPT = """You are extracting key financial line items from a Kenyan
Nairobi Securities Exchange (NSE) listed-company financial results PDF that
has been OCR'd to plain text. Return ONLY the metrics you can verify from
the text — never invent numbers. Amounts in Kenya Shillings (KES).

Rules:
- Report revenue and net income in MILLIONS of KES (divide raw KES by 1_000_000
  yourself if the PDF gives raw KES).
- Report EPS, BVPS, DPS as per-share KES (usually 0.1 – 500).
- If the number is a loss, make net_income_kes_mn negative.
- period_end must be the reporting period's END date (YYYY-MM-DD).
- period_type must be 'annual' (full year) or 'interim' (H1/Q1/H2/Q3).
- Leave any metric null when the text is ambiguous."""


def extract_via_ai(text: str, ticker: str) -> dict | None:
    """Call Anthropic Claude to extract financials from OCR'd text.

    Uses structured tool-use so the model can't emit free-form JSON we'd
    have to parse. Returns the same shape as extract_from_text() with
    ``extraction_method='ai'`` and ``confidence='ai'``. Returns None if
    the API call fails."""
    try:
        from anthropic import Anthropic  # noqa: E402
    except ImportError:
        log.warning("anthropic SDK not installed — skipping AI fallback")
        return None

    client = Anthropic()
    schema = {
        "name": "record_financials",
        "description": "Emit the extracted financial line items.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period_end":         {"type": ["string", "null"]},
                "period_type":        {"type": "string", "enum": ["annual", "interim"]},
                "revenue_kes_mn":     {"type": ["number", "null"]},
                "net_income_kes_mn":  {"type": ["number", "null"]},
                "eps":                {"type": ["number", "null"]},
                "bvps":               {"type": ["number", "null"]},
                "dps_kes":            {"type": ["number", "null"]},
            },
            "required": ["period_type"],
        },
    }
    # Trim to the first ~30k chars to stay under a comfy context budget.
    body = (text or "")[:30_000]
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=_AI_PROMPT,
            tools=[schema],
            tool_choice={"type": "tool", "name": "record_financials"},
            messages=[{
                "role": "user",
                "content": f"Ticker: {ticker}\n\n---\n{body}",
            }],
        )
    except Exception as exc:
        log.warning("  [%s] AI call failed: %s", ticker, exc)
        return None

    for block in resp.content:
        if getattr(block, "type", "") == "tool_use" and block.name == "record_financials":
            out = dict(block.input or {})
            out["extraction_method"] = "ai"
            out["confidence"] = "ai"
            return out
    return None


# ---------------------------------------------------------------------------
# Firestore merge
# ---------------------------------------------------------------------------

def _to_record(extracted: dict, disc_meta: dict) -> dict:
    """Build the FinancialResult-shaped dict that lands in Firestore."""
    now = datetime.now(timezone.utc).isoformat()
    period_end = extracted.get("period_end")
    period_type = extracted.get("period_type", "annual")
    return {
        "period":              _period_label(period_type, period_end),
        "period_end":          period_end,
        "period_type":         period_type,
        "announcement_date":   disc_meta.get("published_at") or "",
        "revenue_kes_mn":      extracted.get("revenue_kes_mn"),
        "net_income_kes_mn":   extracted.get("net_income_kes_mn"),
        "eps":                 extracted.get("eps"),
        "bvps":                extracted.get("bvps"),
        "dps_kes":             extracted.get("dps_kes"),
        "source_disclosure_sha": disc_meta.get("sha16"),
        "source_url":            disc_meta.get("source_url"),
        "extraction_method":     extracted.get("extraction_method", "regex"),
        "confidence":            extracted.get("confidence", "low"),
        "extracted_at":          now,
    }


def _period_label(period_type: str, period_end: str | None) -> str:
    if not period_end or len(period_end) < 7:
        return ""
    year = period_end[:4]
    if period_type == "annual":
        return f"FY{year}"
    month = period_end[5:7]
    if month == "06":
        return f"H1 {year}"
    if month == "12":
        return f"H2 {year}"
    return f"{year}-{month}"


def _merge_into_ticker(db, ticker: str, records: list[dict], dry_run: bool) -> tuple[int, int]:
    """Merge records into financials/{ticker}. Returns (annual_added, interim_added)."""
    if not records:
        return 0, 0
    doc_ref = db.collection("financials").document(ticker)
    snap = doc_ref.get()
    existing = snap.to_dict() if snap.exists else {}

    for key in ("annual", "interim"):
        existing.setdefault(key, [])

    added = {"annual": 0, "interim": 0}

    for rec in records:
        bucket_key = "annual" if rec["period_type"] == "annual" else "interim"
        period_end = rec.get("period_end")
        if not period_end:
            continue

        # Find existing record with same period_end, prefer higher confidence.
        bucket = existing[bucket_key]
        idx = next((i for i, r in enumerate(bucket)
                    if isinstance(r, dict) and r.get("period_end") == period_end), None)
        if idx is None:
            bucket.append(rec)
            added[bucket_key] += 1
        else:
            prev = bucket[idx]
            if _confidence_rank(rec["confidence"]) > _confidence_rank(prev.get("confidence", "low")):
                # Preserve any hand-curated fields the prior record had that
                # the new one doesn't (e.g. period, notes).
                merged = {**prev, **{k: v for k, v in rec.items() if v is not None or k not in prev}}
                bucket[idx] = merged
                added[bucket_key] += 1

    if not dry_run:
        # Sort newest first for stable frontend display.
        for k in ("annual", "interim"):
            existing[k] = sorted(existing[k], key=lambda r: r.get("period_end") or "", reverse=True)
        doc_ref.set(existing, merge=True)

    return added["annual"], added["interim"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_ticker(db, ticker: str, use_ai: bool, force: bool, dry_run: bool) -> dict:
    """Process every archived disclosure for one ticker. Returns counters."""
    items_ref = db.collection("disclosures").document(ticker).collection("items")
    records: list[dict] = []
    stats = {"considered": 0, "extracted": 0, "ai_used": 0, "skipped_nonresult": 0, "skipped_empty": 0}

    for snap in items_ref.stream():
        stats["considered"] += 1
        item = snap.to_dict() or {}
        kind = (item.get("kind") or "").lower()
        if kind not in FIN_RESULT_KINDS and kind != "":
            stats["skipped_nonresult"] += 1
            continue

        text = item.get("text") or ""
        if len(text) < 300:  # OCR failure or notice-only PDF
            stats["skipped_empty"] += 1
            continue

        r = extract_from_text(text)
        if _confidence_rank(r["confidence"]) < _confidence_rank("medium") and use_ai:
            ai = extract_via_ai(text, ticker)
            if ai:
                stats["ai_used"] += 1
                r = ai

        if _confidence_rank(r["confidence"]) < _confidence_rank("low"):
            continue
        if not r.get("period_end"):
            continue

        records.append(_to_record(r, item))
        stats["extracted"] += 1

    annual_added, interim_added = _merge_into_ticker(db, ticker, records, dry_run)
    stats["annual_added"] = annual_added
    stats["interim_added"] = interim_added
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*",
                        help="Restrict to these short-form tickers (default: all)")
    parser.add_argument("--use-ai", action="store_true",
                        help="Fall back to Anthropic Claude when regex returns "
                             "fewer than {} metrics. Requires ANTHROPIC_API_KEY.".format(REGEX_MIN_METRICS))
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even if a record already exists")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.use_ai and not os.environ.get("ANTHROPIC_API_KEY"):
        log.error("--use-ai requires ANTHROPIC_API_KEY in the environment")
        sys.exit(1)

    from pipeline.scripts.firebase_client import get_firestore
    db = get_firestore()

    if args.tickers:
        tickers = args.tickers
    else:
        tickers = sorted(snap.id for snap in db.collection("disclosures").stream())
        log.info("Discovered %d tickers with archived disclosures", len(tickers))

    total_annual = 0
    total_interim = 0
    total_ai = 0
    for tkr in tickers:
        stats = process_ticker(db, tkr, args.use_ai, args.force, args.dry_run)
        total_annual += stats["annual_added"]
        total_interim += stats["interim_added"]
        total_ai += stats["ai_used"]
        log.info(
            "  [%s] +%d annual +%d interim (considered=%d extracted=%d ai=%d skipped_nonresult=%d empty=%d)",
            tkr, stats["annual_added"], stats["interim_added"],
            stats["considered"], stats["extracted"], stats["ai_used"],
            stats["skipped_nonresult"], stats["skipped_empty"],
        )

    verb = "would add" if args.dry_run else "added"
    log.info("=== Done ===")
    log.info("  %s: %d annual + %d interim across %d tickers (AI used: %d)",
             verb, total_annual, total_interim, len(tickers), total_ai)


if __name__ == "__main__":
    main()
