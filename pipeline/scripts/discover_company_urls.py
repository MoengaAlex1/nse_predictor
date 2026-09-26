"""
discover_company_urls — probe candidate website URLs for every NSE-listed
company and write the first working URL back into fundamentals/{ticker}
so enrich_from_ir_pages.py can extract CEO / Chairperson / board.

Root problem the earlier curation pass hit: guessing individual URLs
by hand missed on 7 of 17 (DNS failures, wrong TLDs, SSL cert
mismatches). Rather than keep guessing, generate a battery of
candidate patterns per ticker and let the network decide.

Per ticker (given ticker code + optional short_name from Firestore):
  1. Build a candidate list — common Kenyan corporate domain shapes:
       www.{slug}.co.ke        (the ~60% case)
       {slug}.co.ke
       www.{slug}.com          (regional / multinational subsidiaries)
       {slug}.com
       www.{slug}group.co.ke   (holdings / groups)
       www.{slug}kenya.co.ke
       www.{slug}kenya.com
       www.{slug}ltd.co.ke
     Where slug = ticker.lower() and also a name-derived slug when the
     Firestore doc has short_name / long_name.
  2. HEAD each candidate with a real UA + 8s timeout, follow redirects.
  3. On 200, GET the page and verify the HTML contains the ticker
     symbol OR a substring of the company name — kills false-positive
     domain squatters.
  4. First candidate that verifies wins. Written to
     fundamentals/{ticker}.source_url with confidence:"probed" and
     _probe_matched:<candidate index> so we can audit.

No new vendor introduced: one-way HTTPS to the candidate hostnames,
no third-party API. Runs weekly via GitHub Actions or on demand
after the NSE index scraper.

Usage:
    python pipeline/scripts/discover_company_urls.py [--dry-run] [--tickers ABSA SCOM]
    python pipeline/scripts/discover_company_urls.py --only-missing   # skip tickers already curated
Env: FIREBASE_SERVICE_ACCOUNT_JSON
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
log = logging.getLogger(__name__)

FUNDAMENTALS_JSON = REPO_ROOT / "pipeline" / "config" / "fundamentals.json"

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
        "nse-intelligence/1.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT_S = 8
RATE_LIMIT_S = 0.3   # between candidates for the same ticker
PER_TICKER_MAX = 12  # cap so a ticker with lots of candidate variants doesn't hog runtime


def _slug(s: str) -> str:
    """Normalise a name to a URL-safe slug: lowercase alphanumerics only.
    Drops PLC / Ltd / Group / Holdings suffixes so 'Sasini PLC' → 'sasini'."""
    if not s:
        return ""
    s = s.lower()
    for kill in ("plc", "ltd", "limited", "holdings", "holding", "group", "kenya", "company", "corporation"):
        s = re.sub(rf"\b{kill}\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def candidate_urls(ticker: str, name: str | None) -> list[str]:
    """Generate a battery of plausible corporate URLs for one ticker.

    Ordered by prior-probability: .co.ke first (most common for Kenyan
    listed issuers), then .com for regional/multinational subs, then
    group/holding suffixed variants.
    """
    slug = _slug(ticker)
    name_slug = _slug(name or "")
    seeds: list[str] = []
    # De-dupe while preserving order.
    for s in [name_slug, slug]:
        if s and s not in seeds:
            seeds.append(s)

    patterns = (
        "https://www.{s}.co.ke",
        "https://{s}.co.ke",
        "https://www.{s}.com",
        "https://{s}.com",
        "https://www.{s}group.co.ke",
        "https://www.{s}group.com",
        "https://www.{s}kenya.co.ke",
        "https://www.{s}kenya.com",
        "https://www.{s}holdings.co.ke",
        "https://www.{s}bank.co.ke",
        "https://www.{s}insurance.co.ke",
        "https://{s}.africa",
    )
    # Interleave patterns across seeds so a name-slug and a ticker-slug
    # BOTH get some candidates within the PER_TICKER_MAX cap. Prior
    # code exhausted the first seed's 12 patterns before ever trying
    # the ticker slug — so KPLC (name-slug "powerlighting") never
    # probed www.kplc.co.ke because all 12 slots went to
    # www.powerlighting.co.ke variants.
    out: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for s in seeds:
            url = pattern.format(s=s)
            if url in seen:
                continue
            seen.add(url)
            out.append(url)
            if len(out) >= PER_TICKER_MAX:
                return out
    return out


def verifies(html: str, ticker: str, name: str | None) -> bool:
    """Reject domain-squatter and unrelated-multinational matches. Only
    accept a page that positively references THIS Kenyan issuer.
    Signals in preference order:
      1. NSE-format ISIN prefix (KE00...) — canonical.
      2. Two-or-more distinct company-name tokens (≥4 chars each) — the
         real page nearly always includes the full name.
      3. Ticker code AND a Kenyan-market marker in the same page.
    A generic multinational parent site (e.g. bat.com for BAT plc)
    will fail #2 because it says "BAT" everywhere but doesn't repeat
    the Kenyan short_name; and #3 needs BOTH the ticker and a Kenyan
    marker together, which multinational parents don't have.
    """
    if not html:
        return False
    h = html.lower()

    # 1. ISIN prefix — canonical Kenyan security marker.
    if "ke0" in h or "ke1" in h or "ke2" in h or "ke5" in h or "ke9" in h:
        # Additional guard: ISIN chars must appear near an actual KE isin.
        if re.search(r"\bke[0-9]{10}\b", h):
            return True

    # 2. Multi-token company-name match (strongest signal).
    if name:
        tokens = [t for t in re.split(r"[^a-z0-9]+", name.lower())
                  if len(t) >= 4 and t not in {"plc", "ltd", "limited", "kenya", "group", "holdings", "company", "corporation"}]
        matched = sum(1 for t in tokens if t in h)
        if matched >= 2:
            return True
        # Single-token match when the token is meaningfully specific
        # (>= 6 chars) — most Kenyan corporate identifiers land in that
        # band ("sasini", "kengen", "safaricom"). Also accept when a
        # 4-5 char token appears repeatedly (10+ occurrences suggests
        # the page is genuinely about that entity).
        for t in tokens:
            if t in h:
                if len(t) >= 6:
                    return True
                if h.count(t) >= 10:
                    return True

    # 3. Ticker code AND a Kenyan-market marker together. A ticker cell
    #    lookup ("SCOM", "KCB", "EQTY") that co-occurs with "nairobi
    #    securities exchange" or "nse:{ticker}" is a strong signal.
    tk = ticker.lower()
    if tk in h and ("nairobi securities" in h or f"nse:{tk}" in h or f"nse: {tk}" in h):
        return True
    # Repeated ticker + Kenyan geographical marker — the company's own
    # site nearly always mentions its ticker (or short name) many times
    # alongside "kenya" (address, office, etc.).
    if h.count(tk) >= 5 and "kenya" in h:
        return True

    return False


def probe(url: str) -> tuple[bool, str]:
    """GET a candidate URL. Returns (ok, html_or_reason)."""
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=TIMEOUT_S, allow_redirects=True)
        if r.status_code >= 400:
            return False, f"http_{r.status_code}"
        return True, r.text[:200_000]   # bound memory
    except requests.exceptions.SSLError as e:
        return False, f"ssl_error:{e.__class__.__name__}"
    except requests.exceptions.ConnectionError:
        return False, "conn_error"
    except requests.exceptions.Timeout:
        return False, "timeout"
    except Exception as e:  # noqa: BLE001
        return False, f"error:{e.__class__.__name__}"


def discover_one(ticker: str, name: str | None) -> dict | None:
    """Probe every candidate for one ticker; return the first verified
    match as {url, matched_at, name_used_for_verify}."""
    cands = candidate_urls(ticker, name)
    for i, url in enumerate(cands):
        ok, body = probe(url)
        if not ok:
            log.debug("  [%s] %s → %s", ticker, url, body)
            time.sleep(RATE_LIMIT_S)
            continue
        if not verifies(body, ticker, name):
            log.debug("  [%s] %s → 200 but verify failed", ticker, url)
            time.sleep(RATE_LIMIT_S)
            continue
        log.info("  [%s] ✓ %s (candidate #%d)", ticker, url, i + 1)
        return {"url": url, "matched_at": i, "candidate_count": len(cands)}
    log.info("  [%s] ✗ no candidate matched (%d tried)", ticker, len(cands))
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs="*", help="Restrict to these tickers (default: all listed in fundamentals.json)")
    parser.add_argument("--only-missing", action="store_true", help="Skip tickers that already have source_url")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to fundamentals.json / Firestore")
    args = parser.parse_args()

    with open(FUNDAMENTALS_JSON, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Discover which tickers to probe. If --tickers, honor it; else the
    # union of fundamentals.json keys + any Firestore tickers not in it.
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = sorted(k for k in cfg.keys() if k != "_meta")
        # Also pull the full list from Firestore so we probe tickers not
        # yet in fundamentals.json (e.g. new listings the scraper found).
        try:
            from pipeline.scripts.firebase_client import get_firestore
            db = get_firestore()
            for snap in db.collection("companies").stream():
                t = snap.id
                if t not in cfg and t not in tickers:
                    tickers.append(t)
            tickers = sorted(tickers)
            log.info("Discovered %d tickers to probe (fundamentals.json + Firestore companies)", len(tickers))
        except Exception as e:
            log.warning("Firestore lookup failed (%s) — using fundamentals.json only", e)

    if args.only_missing:
        tickers = [t for t in tickers if not (cfg.get(t) or {}).get("source_url")]
        log.info("--only-missing narrowed to %d tickers", len(tickers))

    # Get company display names — the verify heuristic and slug
    # generator both need them. Prefer Firestore (fresh), fall back to
    # the `source` field in fundamentals.json which usually starts with
    # the full name ("Safaricom PLC Annual Report ..."), or the `name`
    # field if a prior scraper added it.
    names: dict[str, str] = {}
    for t in tickers:
        entry = cfg.get(t) or {}
        if entry.get("name"):
            names[t] = entry["name"]
        else:
            src = entry.get("source") or ""
            m = re.match(r"^([A-Za-z0-9 &\-'\.]+?)(?:\s+(?:PLC|Ltd|Limited|Bank|Group|Holdings|Insurance|Company|Corporation|Investor|Annual|FY|Q[1-4]|H[12])\b|$)", src)
            if m:
                names[t] = m.group(1).strip()

    try:
        from pipeline.scripts.firebase_client import get_firestore
        db = get_firestore()
        for t in tickers:
            snap = db.collection("companies").document(t).get()
            if snap.exists:
                d = snap.to_dict() or {}
                fresh = d.get("name") or d.get("long_name") or ""
                if fresh:
                    names[t] = fresh
    except Exception as e:
        log.warning("Firestore name lookup failed (%s) — using fundamentals.json fallback", e)

    now = datetime.now(timezone.utc).isoformat()
    counters = {"found": 0, "notfound": 0}
    for tkr in tickers:
        found = discover_one(tkr, names.get(tkr))
        if not found:
            counters["notfound"] += 1
            continue
        counters["found"] += 1
        entry = cfg.get(tkr) or {}
        entry.update({
            "source_url": found["url"],
            "confidence": "probed",
            "method": "url_discovery",
            "source": f"discovered by discover_company_urls.py (candidate {found['matched_at']+1}/{found['candidate_count']})",
            "discovered_at": now,
        })
        cfg[tkr] = entry

    if not args.dry_run:
        cfg.setdefault("_meta", {})
        cfg["_meta"]["last_url_discovery"] = now
        with open(FUNDAMENTALS_JSON, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            f.write("\n")
        log.info("Wrote %s", FUNDAMENTALS_JSON)

    log.info("=== Done ===")
    log.info("  found: %d  notfound: %d", counters["found"], counters["notfound"])


if __name__ == "__main__":
    main()
