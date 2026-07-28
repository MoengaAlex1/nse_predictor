"""
Merge PDF-extracted financial data with existing financials.json and re-seed Firestore.

Strategy:
  - For each ticker, start with existing data from financials.json
  - Overlay PDF-extracted records where they have better data
  - Prefer extracted data for years where we have it (more accurate, directly from filings)
  - Keep manual data for years where no PDF was extracted

Usage:
    python pipeline/scripts/merge_and_seed_extracted.py [--dry-run] [--tickers KCB_NR ...]
"""

import json
import sys
from pathlib import Path
from typing import Any, Optional

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.push_to_firestore import get_db

FINANCIALS_CONFIG = PIPELINE_ROOT / "config" / "financials.json"
EXTRACTED_DIR = PIPELINE_ROOT / "data" / "extracted"


def load_existing() -> dict:
    if FINANCIALS_CONFIG.exists():
        with open(FINANCIALS_CONFIG, encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_extracted() -> dict:
    extracted = {}
    for path in EXTRACTED_DIR.glob("*.json"):
        if path.name == "all_extracted.json":
            continue
        ticker = path.stem
        data = json.load(open(path, encoding="utf-8"))
        records = data.get("extracted", [])
        if records:
            extracted[ticker] = records
    return extracted


def record_key(r: dict) -> str:
    """Unique key for deduplication: period_end or period label."""
    return r.get("period_end") or r.get("period", "unknown")


def merge_records(existing_list: list, extracted_list: list) -> list:
    """
    Merge two lists of annual financial records.
    For the same period_end/period, prefer extracted data if it has more non-null fields.
    """
    by_key: dict[str, dict] = {}

    # Load existing first
    for r in existing_list:
        k = record_key(r)
        by_key[k] = r.copy()

    # Overlay with extracted data
    for ext in extracted_list:
        k = record_key(ext)
        if k == "unknown":
            continue

        existing = by_key.get(k, {})
        merged = {**existing}

        # Map extracted field names to Firestore schema field names
        field_map = {
            "revenue_kes_mn": "revenue_kes_mn",
            "net_income_kes_mn": "net_income_kes_mn",
            "eps": "eps",
            "dps": "dps",
            "bvps": "bvps",
            "period": "period",
            "period_end": "period_end",
            "period_type": "period_type",
        }

        for ext_field, schema_field in field_map.items():
            val = ext.get(ext_field)
            if val is not None:
                merged[schema_field] = val

        # --- Post-merge sanity corrections ---
        pat = merged.get("net_income_kes_mn")
        eps = merged.get("eps")
        existing_pat = existing.get("net_income_kes_mn")
        existing_eps = existing.get("eps")
        existing_rev = existing.get("revenue_kes_mn")

        # Fix sign inconsistency: if EPS is positive but PAT is negative, flip PAT
        if pat is not None and eps is not None and pat < 0 and eps > 0:
            merged["net_income_kes_mn"] = abs(pat)
            pat = merged["net_income_kes_mn"]

        # Reject implausible EPS (years or large account numbers extracted as EPS)
        if eps is not None and (eps > 500 or eps < -500):
            merged.pop("eps", None)
            eps = None

        # EPS ratio guard: if extracted EPS is >10x or <1/10 of existing, fall back
        if eps is not None and existing_eps is not None and existing_eps != 0:
            eps_ratio = abs(eps) / abs(existing_eps)
            if eps_ratio > 10 or eps_ratio < 0.1:
                merged["eps"] = existing_eps
                eps = existing_eps

        # Absolute PAT cap: fall back to existing if extracted is implausible
        if pat is not None and abs(pat) > 90_000:
            if existing_pat is not None:
                merged["net_income_kes_mn"] = existing_pat
            else:
                merged.pop("net_income_kes_mn", None)
            pat = merged.get("net_income_kes_mn")

        # Ratio guard: if extracted PAT is >50x or <1/50 of existing, fall back
        if pat is not None and existing_pat is not None and existing_pat != 0:
            ratio = abs(pat) / abs(existing_pat)
            if ratio > 50 or ratio < 0.02:
                merged["net_income_kes_mn"] = existing_pat
                pat = merged["net_income_kes_mn"]

        # Same checks for revenue
        rev = merged.get("revenue_kes_mn")

        # Absolute revenue cap: fall back to existing if extracted is implausible
        if rev is not None and rev > 500_000:
            if existing_rev is not None:
                merged["revenue_kes_mn"] = existing_rev
            else:
                merged.pop("revenue_kes_mn", None)
            rev = merged.get("revenue_kes_mn")

        if rev is not None and existing_rev is not None and existing_rev != 0:
            ratio = abs(rev) / abs(existing_rev)
            if ratio > 50 or ratio < 0.02:
                merged["revenue_kes_mn"] = existing_rev

        by_key[k] = merged

    # Sort by period_end descending, then by period label
    result = sorted(
        by_key.values(),
        key=lambda r: (r.get("period_end") or r.get("period", ""), ),
        reverse=True,
    )
    return result


def seed_ticker(db: Any, ticker: str, annual: list, existing_doc: dict) -> None:
    doc = {
        "annual": annual,
        "dividends": existing_doc.get("dividends", []),
        "corporate_actions": existing_doc.get("corporate_actions", []),
    }
    db.collection("financials").document(ticker).set(doc, merge=False)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Merge PDF-extracted data and seed Firestore")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't write to Firestore")
    parser.add_argument("--tickers", nargs="*", help="Specific tickers to process")
    args = parser.parse_args()

    existing_all = load_existing()
    extracted_all = load_extracted()

    target_tickers = set(args.tickers) if args.tickers else (
        set(existing_all.keys()) | set(extracted_all.keys())
    )

    print(f"Existing financials.json tickers: {len(existing_all)}")
    print(f"Extracted tickers with data: {len(extracted_all)}")
    print(f"Target tickers: {len(target_tickers)}")

    if not args.dry_run:
        db = get_db()

    seeded = 0
    for ticker in sorted(target_tickers):
        existing_doc = existing_all.get(ticker, {})
        existing_annual = existing_doc.get("annual", [])
        extracted_records = extracted_all.get(ticker, [])

        merged = merge_records(existing_annual, extracted_records)

        # Filter: only keep annual records (not interim) and only those with at least one metric
        annual_only = [
            r for r in merged
            if r.get("period_type", "annual") == "annual"
            and any(r.get(f) is not None for f in ["revenue_kes_mn", "net_income_kes_mn", "eps"])
        ]

        # Also keep any interim records that have EPS
        interim = [
            r for r in merged
            if r.get("period_type") == "interim"
            and r.get("eps") is not None
        ]

        final = sorted(annual_only + interim, key=lambda r: r.get("period_end") or "", reverse=True)

        extracted_count = len([r for r in extracted_records if r.get("period_end")])
        print(f"\n[{ticker}] existing={len(existing_annual)} extracted={extracted_count} merged={len(final)}")

        for r in final[:5]:
            print(f"  {r.get('period', '?'):20} rev={str(r.get('revenue_kes_mn', '-')):>12} "
                  f"pat={str(r.get('net_income_kes_mn', '-')):>10} eps={r.get('eps', '-')}")

        if not args.dry_run and final:
            seed_ticker(db, ticker, final, existing_doc)
            seeded += 1

    if args.dry_run:
        print(f"\n[DRY RUN] Would seed {len(target_tickers)} tickers")
    else:
        print(f"\n=== Done === Seeded {seeded} tickers to Firestore financials/")


if __name__ == "__main__":
    main()
