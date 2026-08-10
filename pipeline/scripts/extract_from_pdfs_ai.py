"""
Extract structured financials from NSE PDF disclosures using Claude.

For each ticker in Firestore's financials/{ticker} doc:
 1. Find the most recent audited-annual-result PDF from the .announcements
    array (populated by refresh_nse_disclosures.py).
 2. Download the PDF from NSE's WordPress media host.
 3. Send it to Claude's PDF endpoint with a strict JSON-schema prompt.
 4. Write extracted results to:
      financials/{ticker}.annual  — array merged by period, most recent first
      fundamentals/{ticker}       — shares_outstanding, updated_at

Optionally: for each pending dividend record (amount_kes == None) in the
same financials doc, fetch the dividend-notice PDF and extract
amount_kes + ex_date + payment_date.

Cost: ~5-8K input tokens per PDF at Sonnet pricing (~$0.02/PDF), so a
full 60-ticker run is ~$1.20 in API tokens. Rate-limited to 1 req/sec.

Usage:
    python pipeline/scripts/extract_from_pdfs_ai.py [--tickers SCOM KCB] [--dry-run]
                                                    [--annual-only] [--dividends-only]
Env: ANTHROPIC_API_KEY, FIREBASE_SERVICE_ACCOUNT_JSON
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

CLAUDE_MODEL = "claude-sonnet-4-6"
NVIDIA_MODEL = "meta/muse-glimmer-30b"
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MAX_ANNUAL_PDF_MB = 30  # Claude limit is ~32 MB
MAX_TOKENS = 1200
RATE_LIMIT_SECONDS = 1.0
# Text-mode extraction cap. Muse Glimmer 30B has 131K context; NSE annual
# reports are usually 30-80 pages / 40-80K tokens. Truncate at 400K chars
# (~100K tokens conservatively) so we never overshoot.
MAX_TEXT_CHARS = 400_000

# The extraction is only useful if we can trust the numbers. Give Claude
# tight schema + explicit "prefer null over guessing" rule.
ANNUAL_SYSTEM_PROMPT = (
    "You are a forensic accountant extracting audited financial data from "
    "Nairobi Securities Exchange annual report PDFs. Rules: only return "
    "numbers you can directly read from the document. Prefer null over "
    "guessing. Convert all currency to KES. Numbers in KES millions unless "
    "noted otherwise. Return ONLY valid JSON — no prose, no markdown fences."
)

ANNUAL_USER_PROMPT = """
Extract this exact JSON schema from the attached NSE annual report PDF:

{
  "period":              "<FY2024 / FY2025 / H1 2025 / etc.>",
  "period_end":          "<YYYY-MM-DD ending date of the reporting period>",
  "period_type":         "<annual | interim>",
  "announcement_date":   "<YYYY-MM-DD date the results were announced, if in PDF>",
  "revenue_kes_mn":      <number in KES millions or null>,
  "net_income_kes_mn":   <number in KES millions or null>,
  "eps":                 <basic EPS in KES per share or null>,
  "bvps":                <book value per share in KES or null>,
  "shares_outstanding_mn": <ordinary shares in issue, in millions, or null>,
  "dividend_per_share":  <full-year DPS in KES per share or null>,
  "dividend_type":       "<interim | final | total | none>",
  "extraction_confidence": "<high | medium | low — how legible was the source>",
  "notes":               "<optional 1-line comment on any anomalies>"
}

Return only that JSON object. No fences. If the PDF is not an audited or
half-year financial result (e.g. it's a dividend notice or corporate
action), return {"period": null, "extraction_confidence": "low",
"notes": "not a financial result PDF"}.
"""

DIVIDEND_SYSTEM_PROMPT = (
    "You are a data extractor pulling dividend details from NSE dividend "
    "notice PDFs. Only return numbers you can read directly. Prefer null "
    "over guessing. Return ONLY valid JSON — no prose."
)

DIVIDEND_USER_PROMPT = """
Extract this exact JSON schema from the attached NSE dividend notice PDF:

{
  "amount_kes":       <per-share dividend amount in KES or null>,
  "ex_date":          "<YYYY-MM-DD book closure / ex-dividend date or null>",
  "payment_date":     "<YYYY-MM-DD payment date or null>",
  "type":             "<interim | final | special | scrip | bonus>",
  "period_end":       "<YYYY-MM-DD reporting-period ending date or null>",
  "extraction_confidence": "<high | medium | low>"
}

Return only that JSON object. No fences.
"""

# ── Function-calling schemas for NVIDIA path ──────────────────────────────
# Muse Glimmer doesn't support Structured Output (per the model card) but
# does support Function Calling — we use it to force schema compliance.

ANNUAL_TOOL = {
    "type": "function",
    "function": {
        "name": "record_extracted_financials",
        "description": "Record structured financial data pulled from a Nairobi Securities Exchange audited annual result PDF.",
        "parameters": {
            "type": "object",
            "properties": {
                "period":                {"type": "string", "description": "e.g. FY2024 or H1 2025"},
                "period_end":            {"type": "string", "description": "YYYY-MM-DD"},
                "period_type":           {"type": "string", "enum": ["annual", "interim"]},
                "announcement_date":     {"type": "string", "description": "YYYY-MM-DD"},
                "revenue_kes_mn":        {"type": ["number", "null"], "description": "KES millions"},
                "net_income_kes_mn":     {"type": ["number", "null"], "description": "KES millions"},
                "eps":                   {"type": ["number", "null"], "description": "basic EPS in KES per share"},
                "bvps":                  {"type": ["number", "null"], "description": "book value per share in KES"},
                "shares_outstanding_mn": {"type": ["number", "null"], "description": "ordinary shares in issue, millions"},
                "dividend_per_share":    {"type": ["number", "null"], "description": "full-year DPS in KES"},
                "dividend_type":         {"type": "string", "enum": ["interim", "final", "total", "none"]},
                "extraction_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "notes":                 {"type": "string"},
            },
            "required": ["period", "extraction_confidence"],
        },
    },
}

DIVIDEND_TOOL = {
    "type": "function",
    "function": {
        "name": "record_extracted_dividend",
        "description": "Record dividend details pulled from a Nairobi Securities Exchange dividend notice PDF.",
        "parameters": {
            "type": "object",
            "properties": {
                "amount_kes":            {"type": ["number", "null"], "description": "per-share amount in KES"},
                "ex_date":               {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                "payment_date":          {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                "type":                  {"type": "string", "enum": ["interim", "final", "special", "scrip", "bonus"]},
                "period_end":            {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                "extraction_confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            },
            "required": ["extraction_confidence"],
        },
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_latest_annual_url(announcements: list[dict]) -> dict | None:
    """Pick the most-recent PDF whose title/URL looks like an audited annual
    (or half-year) result. Skips interim quarterly reports."""
    if not announcements:
        return None
    scored = []
    for a in announcements:
        title = (a.get("title") or "").lower()
        url = (a.get("url") or "").lower()
        text = title + " " + url
        if not text.strip():
            continue
        score = 0
        if "audited" in text or "annual report" in text or "integrated report" in text:
            score = 3
        elif "half year" in text or "half-year" in text or "h1" in text or "interim result" in text:
            score = 2
        elif "financial result" in text or "financial statement" in text:
            score = 1
        if score == 0:
            continue
        scored.append((score, a.get("date") or "", a))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return scored[0][2]


def download_pdf(url: str, tmpdir: Path) -> Path | None:
    tmpdir.mkdir(parents=True, exist_ok=True)
    fname = url.rsplit("/", 1)[-1] or "download.pdf"
    fname = re.sub(r"[^A-Za-z0-9_.-]", "_", fname)[:100]
    dest = tmpdir / fname
    try:
        r = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            print(f"    ! download HTTP {r.status_code}")
            return None
        size_mb = len(r.content) / 1_000_000
        if size_mb > MAX_ANNUAL_PDF_MB:
            print(f"    ! PDF too large ({size_mb:.1f} MB > {MAX_ANNUAL_PDF_MB} MB)")
            return None
        dest.write_bytes(r.content)
        return dest
    except requests.RequestException as exc:
        print(f"    ! download error: {exc}")
        return None


def _b64_encode(pdf_path: Path) -> str:
    return base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")


# ---------------------------------------------------------------------------
# Regex fallback — best-effort pdfplumber+regex when Claude isn't available.
# Accuracy is materially lower than Claude's; use only when necessary.
# ---------------------------------------------------------------------------

_KES_NUM = re.compile(r"\(?[Kk]?[Ss]?[Hh]?[Ss]?\.?\s*([\d,]+(?:\.\d+)?)\)?")

REGEX_PATTERNS = {
    "revenue_kes_mn":       [r"(?:total\s+)?(?:revenue|net\s+interest\s+income|turnover)[\s:]{0,5}", 1_000_000],
    "net_income_kes_mn":    [r"(?:profit\s+after\s+tax|net\s+(?:profit|income|earnings?)|pat)[\s:]{0,5}", 1_000_000],
    "eps":                  [r"(?:basic\s+)?earnings?\s+per\s+share(?:\s*\([^)]{0,20}\))?[\s:]{0,5}", 1],
    "bvps":                 [r"(?:book\s+value\s+per\s+share|nav\s+per\s+share)[\s:]{0,5}", 1],
    "dividend_per_share":   [r"(?:dividend\s+per\s+share|proposed\s+dividend|dps)[\s:]{0,5}", 1],
    "shares_outstanding_mn": [r"(?:ordinary\s+shares\s+in\s+issue|number\s+of\s+shares\s+in\s+issue|weighted\s+average\s+number\s+of\s+ordinary\s+shares)[\s:]{0,15}", 1_000_000],
}


def _parse_num(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def extract_via_regex(pdf_path: Path) -> dict:
    """Best-effort pdfplumber+regex. Populates whatever fields match; leaves
    the rest as None. Never fabricates."""
    try:
        import pdfplumber
    except ImportError:
        print("    ! pdfplumber missing — pip install pdfplumber")
        return {}

    try:
        with pdfplumber.open(pdf_path) as pdf:
            texts = []
            for page in pdf.pages[:30]:  # cap at first 30 pages
                t = page.extract_text() or ""
                texts.append(t)
            full = "\n".join(texts)
    except Exception as exc:
        print(f"    ! pdfplumber error: {exc}")
        return {}

    out: dict = {"period": None, "period_type": "annual", "extraction_confidence": "low"}

    for field, (label_re, scale) in REGEX_PATTERNS.items():
        pat = re.compile(label_re + _KES_NUM.pattern, re.IGNORECASE)
        m = pat.search(full)
        if not m:
            continue
        val = _parse_num(m.group(1))
        if val is None:
            continue
        # Sanity scaling
        if field in ("revenue_kes_mn", "net_income_kes_mn"):
            # Big number; scale down to millions if in absolute
            out[field] = round(val / 1_000, 1) if val >= 1_000_000 else round(val, 1)
        elif field == "shares_outstanding_mn":
            out[field] = round(val / 1_000_000, 1) if val >= 1_000_000 else round(val, 1)
        else:
            out[field] = round(val, 2)

    # Period extraction: search for "year ended DD-MM-YYYY" or similar
    period_m = re.search(
        r"(?:year|period)\s+ended?\s+"
        r"(\d{1,2})[\s\-/]([A-Za-z]{3,9})[\s\-/](\d{2,4})",
        full,
        re.IGNORECASE,
    )
    if period_m:
        day, month_str, year = period_m.group(1), period_m.group(2).lower()[:3], period_m.group(3)
        months = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
                  "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
        if month_str in months and len(year) in (2, 4):
            year_full = year if len(year) == 4 else f"20{year}"
            try:
                iso = f"{year_full}-{months[month_str]}-{int(day):02d}"
                datetime.fromisoformat(iso)  # validate
                out["period_end"] = iso
                out["period"] = f"FY{year_full}"
            except ValueError:
                pass

    # Confidence: high if we got 3+ core fields
    got = sum(1 for k in ("revenue_kes_mn", "net_income_kes_mn", "eps") if out.get(k) is not None)
    out["extraction_confidence"] = ["low", "low", "medium", "high"][min(got, 3)]
    return out


def _pdf_to_text(pdf_path: Path, max_pages: int = 100) -> str:
    """Extract text from a PDF via pdfplumber. Returns "" if not extractable
    (scanned image PDF, corrupt, etc.). Caller decides how to handle empty."""
    try:
        import pdfplumber
    except ImportError:
        return ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            parts = []
            for page in pdf.pages[:max_pages]:
                t = page.extract_text() or ""
                parts.append(t)
            return "\n".join(parts).strip()
    except Exception:
        return ""


def extract_via_nvidia(client, pdf_path: Path, system_prompt: str, user_prompt: str, tool: dict) -> dict | None:
    """Text-mode extraction via NVIDIA-hosted model (Muse Glimmer 30B) using
    OpenAI-compat function calling. Muse Glimmer accepts images too, but
    for typed NSE reports pdfplumber gets clean text — image mode would
    just add token cost with no accuracy gain."""
    pdf_text = _pdf_to_text(pdf_path)
    if not pdf_text or len(pdf_text) < 200:
        print(f"    ! PDF text too short ({len(pdf_text)} chars) — likely scanned; skip")
        return None
    if len(pdf_text) > MAX_TEXT_CHARS:
        pdf_text = pdf_text[:MAX_TEXT_CHARS] + "\n[...truncated...]"

    fn_name = tool["function"]["name"]
    # Muse Glimmer's /chat/completions endpoint tolerates ~100K prompt tokens.
    # If the OpenAI SDK's outer "Connection error" wraps a real HTTP status
    # (413 payload too large, 400 bad request, 429 rate limit, 401 auth), the
    # inner __cause__ carries the actual response — surface it so we can act.
    try:
        response = client.chat.completions.create(
            model=NVIDIA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}\n\n=== PDF TEXT ===\n{pdf_text}"},
            ],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": fn_name}},
            temperature=0.1,
            max_tokens=MAX_TOKENS,
            timeout=120.0,  # explicit — SDK default is 60s and this is a big prompt
        )
    except Exception as exc:
        cause = getattr(exc, "__cause__", None)
        detail = f" (cause: {type(cause).__name__}: {cause})" if cause else ""
        # OpenAI APIError carries .status_code + .response, if present
        status = getattr(exc, "status_code", None)
        body = getattr(getattr(exc, "response", None), "text", None)
        extra = f" [status={status}]" if status else ""
        if body:
            extra += f" body={body[:300]}"
        print(f"    ! NVIDIA API error: {type(exc).__name__}: {exc}{extra}{detail}")
        print(f"    ! prompt size: {len(pdf_text)} chars")
        return None

    msg = response.choices[0].message
    tool_calls = getattr(msg, "tool_calls", None)
    finish_reason = response.choices[0].finish_reason
    print(f"    · finish_reason={finish_reason}, tool_calls={bool(tool_calls)}")
    if not tool_calls:
        # Some models forget the tool call when the tool_choice hint is
        # weak; try to salvage from the text content as JSON fallback.
        raw = (msg.content or "").strip()
        print(f"    · text content ({len(raw)} chars): {raw[:400]}")
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        try:
            parsed = json.loads(raw)
            print(f"    · parsed keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'not-a-dict'}")
            return parsed
        except json.JSONDecodeError:
            print(f"    ! no tool call and text not JSON: {raw[:200]}")
            return None
    try:
        args_raw = tool_calls[0].function.arguments
        print(f"    · tool call arg length: {len(args_raw)}")
        parsed = json.loads(args_raw)
        print(f"    · parsed keys: {list(parsed.keys())}")
        return parsed
    except json.JSONDecodeError as exc:
        print(f"    ! tool call args not JSON: {exc}. Raw: {args_raw[:300]}")
        return None


def extract_via_claude(client, pdf_path: Path, system_prompt: str, user_prompt: str) -> dict | None:
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": _b64_encode(pdf_path),
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ],
        )
    except Exception as exc:
        print(f"    ! Claude API error: {exc}")
        return None

    raw = msg.content[0].text.strip()
    # Strip common markdown-fence noise even though we asked not to.
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"    ! non-JSON response: {raw[:200]}")
        return None


def merge_annual(existing_annual: list[dict], new_row: dict) -> list[dict]:
    """Insert/replace by period key, sort by period_end desc."""
    period = new_row.get("period")
    if not period:
        return existing_annual
    merged = [r for r in existing_annual if r.get("period") != period]
    merged.append(new_row)
    return sorted(merged, key=lambda r: r.get("period_end") or "", reverse=True)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_ticker_annual(client, db, ticker: str, tmpdir: Path, dry_run: bool, engine: str = "regex") -> bool:
    doc_ref = db.collection("financials").document(ticker)
    snap = doc_ref.get()
    existing = snap.to_dict() if snap.exists else {}
    announcements = existing.get("announcements", [])

    latest = find_latest_annual_url(announcements)
    if not latest:
        print(f"  [{ticker}] no annual result URL — skip")
        return False

    url = latest.get("url")
    print(f"  [{ticker}] downloading {url.rsplit('/', 1)[-1][:60]}")
    pdf_path = download_pdf(url, tmpdir)
    if not pdf_path:
        return False

    if engine == "nvidia":
        print(f"  [{ticker}] extracting via NVIDIA...")
        parsed = extract_via_nvidia(client, pdf_path, ANNUAL_SYSTEM_PROMPT, ANNUAL_USER_PROMPT, ANNUAL_TOOL)
    elif engine == "claude":
        print(f"  [{ticker}] extracting via Claude...")
        parsed = extract_via_claude(client, pdf_path, ANNUAL_SYSTEM_PROMPT, ANNUAL_USER_PROMPT)
    else:
        print(f"  [{ticker}] extracting via regex fallback...")
        parsed = extract_via_regex(pdf_path)
    if not parsed or not parsed.get("period"):
        print(f"  [{ticker}] no usable extraction")
        return False

    print(
        f"  [{ticker}] {parsed.get('period')}  eps={parsed.get('eps')}  "
        f"rev={parsed.get('revenue_kes_mn')}  shares={parsed.get('shares_outstanding_mn')}"
    )

    if dry_run:
        return True

    # Financials annual merge
    annual_row = {
        "period":            parsed.get("period"),
        "period_end":        parsed.get("period_end"),
        "period_type":       parsed.get("period_type") or "annual",
        "announcement_date": parsed.get("announcement_date"),
        "revenue_kes_mn":    parsed.get("revenue_kes_mn"),
        "net_income_kes_mn": parsed.get("net_income_kes_mn"),
        "eps":               parsed.get("eps"),
        "bvps":              parsed.get("bvps"),
        "source":            "claude-extraction",
    }
    merged_annual = merge_annual(existing.get("annual", []), annual_row)
    doc_ref.set({"annual": merged_annual}, merge=True)
    print(f"  [{ticker}] wrote financials/{ticker}.annual (total {len(merged_annual)})")

    # Fundamentals: shares_outstanding, DPS
    fund_ref = db.collection("fundamentals").document(ticker)
    fund_snap = fund_ref.get()
    fund_existing = fund_snap.to_dict() if fund_snap.exists else {}
    fund_updates = {"ticker": ticker, "updated_at": datetime.now(timezone.utc).isoformat()}
    if parsed.get("shares_outstanding_mn") is not None:
        fund_updates["shares_outstanding_mn"] = parsed["shares_outstanding_mn"]
    # Preserve fields already there
    for k in ("enterprise_value_kes_bn", "employees", "estimates"):
        if k in fund_existing and k not in fund_updates:
            fund_updates[k] = fund_existing[k]
    fund_ref.set(fund_updates, merge=True)
    print(f"  [{ticker}] wrote fundamentals/{ticker}")

    return True


def process_ticker_dividends(client, db, ticker: str, tmpdir: Path, dry_run: bool, engine: str = "regex") -> int:
    """Fill in amount_kes + ex_date + payment_date for dividend records that
    only have URL + title. Returns count of records updated."""
    doc_ref = db.collection("financials").document(ticker)
    snap = doc_ref.get()
    if not snap.exists:
        return 0
    existing = snap.to_dict()
    dividends = existing.get("dividends", [])
    pending = [d for d in dividends if d.get("amount_kes") is None and d.get("url")]
    # Only process the 3 most recent to keep cost bounded
    pending = pending[:3]

    if not pending:
        return 0

    if engine == "regex" or client is None:
        # Dividend-notice PDFs vary too widely for reliable regex extraction
        # (amount can be in a footnote, ex-date in a table, etc.). Skip
        # gracefully rather than mangle the record.
        return 0

    updated_count = 0
    for div in pending:
        url = div["url"]
        print(f"  [{ticker}] dividend PDF: {url.rsplit('/', 1)[-1][:60]}")
        pdf_path = download_pdf(url, tmpdir)
        if not pdf_path:
            continue
        if engine == "nvidia":
            parsed = extract_via_nvidia(client, pdf_path, DIVIDEND_SYSTEM_PROMPT, DIVIDEND_USER_PROMPT, DIVIDEND_TOOL)
        else:
            parsed = extract_via_claude(client, pdf_path, DIVIDEND_SYSTEM_PROMPT, DIVIDEND_USER_PROMPT)
        if not parsed:
            continue
        # Only apply fields that were parsed; keep title/url/source intact
        for k in ("amount_kes", "ex_date", "payment_date", "type", "period_end"):
            v = parsed.get(k)
            if v is not None:
                div[k] = v
        div["extraction_confidence"] = parsed.get("extraction_confidence", "low")
        updated_count += 1
        print(f"    -> amount={div.get('amount_kes')} ex_date={div.get('ex_date')}")
        time.sleep(RATE_LIMIT_SECONDS)

    if updated_count and not dry_run:
        doc_ref.set({"dividends": dividends}, merge=True)
        print(f"  [{ticker}] wrote {updated_count} enriched dividend records")

    return updated_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*", help="Bare tickers to process (default: all)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--annual-only", action="store_true")
    parser.add_argument("--dividends-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Cap on ticker count")
    args = parser.parse_args()

    from scripts.firebase_client import get_firestore
    db = get_firestore()

    # Engine priority: NVIDIA (function calling, high accuracy on text) →
    # Claude (native PDF, high accuracy) → regex (pdfplumber patterns, low).
    # Whichever key is set first in that order wins. Both keys set → NVIDIA.
    #
    # Strip whitespace defensively — a common paste-into-`gh secret set`
    # failure mode is a trailing newline that turns into an "Illegal header
    # value" error deep inside httpx.
    nvidia_key = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    anthropic_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

    if nvidia_key and not nvidia_key.startswith("nvapi-"):
        print(f"WARNING: NVIDIA_API_KEY doesn't start with 'nvapi-' (got '{nvidia_key[:10]}...'). "
              f"Ignoring — probably pasted the wrong value into the secret.")
        nvidia_key = ""
    if nvidia_key and ("\n" in nvidia_key or "\r" in nvidia_key or " " in nvidia_key):
        print(f"WARNING: NVIDIA_API_KEY contains whitespace after strip. Ignoring.")
        nvidia_key = ""

    engine = None
    client = None
    if nvidia_key:
        from openai import OpenAI
        client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=nvidia_key)
        engine = "nvidia"
        print(f"Extraction engine: NVIDIA {NVIDIA_MODEL}")
    elif anthropic_key:
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        engine = "claude"
        print(f"Extraction engine: Claude ({CLAUDE_MODEL})")
    else:
        engine = "regex"
        print("Extraction engine: pdfplumber+regex (no NVIDIA_API_KEY or ANTHROPIC_API_KEY set)")

    # Find eligible tickers — every ticker with a financials doc
    fin_docs = list(db.collection("financials").stream())
    all_tickers = sorted(d.id for d in fin_docs)
    if args.tickers:
        want = {t.upper() for t in args.tickers}
        tickers = [t for t in all_tickers if t.upper() in want]
    else:
        tickers = all_tickers
    if args.limit:
        tickers = tickers[: args.limit]

    print(f"Processing {len(tickers)} tickers: {tickers[:10]}{'...' if len(tickers) > 10 else ''}\n")

    tmpdir = Path("/tmp/nse-pdfs") if os.name != "nt" else Path.home() / "AppData" / "Local" / "Temp" / "nse-pdfs"

    annual_hits = 0
    dividend_hits = 0

    for tkr in tickers:
        print(f"\n=== {tkr} ===")

        if not args.dividends_only:
            if process_ticker_annual(client, db, tkr, tmpdir, args.dry_run, engine=engine):
                annual_hits += 1
            time.sleep(RATE_LIMIT_SECONDS)

        if not args.annual_only:
            dividend_hits += process_ticker_dividends(client, db, tkr, tmpdir, args.dry_run, engine=engine)

    print(f"\n=== Done === annual: {annual_hits}/{len(tickers)}, dividend records: {dividend_hits}")


if __name__ == "__main__":
    main()
