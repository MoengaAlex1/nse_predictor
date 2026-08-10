"""
Seed curated financials + fundamentals into Firestore at bare-ticker doc IDs.

Two data sources:
  pipeline/config/financials.json    -> per-ticker annual results + dividends
                                        Keyed by "_NR"-suffixed tickers
                                        (legacy). We strip the suffix at write
                                        time so docs land at the bare ticker
                                        Firestore convention (financials/SCOM,
                                        not financials/SCOM_NR).
  pipeline/config/fundamentals.json  -> shares_outstanding_mn per ticker,
                                        keyed by bare tickers.
                                        For tickers missing from the curated
                                        list, we back-derive
                                        shares = net_income_kes_mn / eps
                                        from the most recent annual row in
                                        financials.json (mathematically
                                        exact — audited numbers are
                                        self-consistent).

The seed is idempotent (merge=True). Existing Firestore docs are
extended, not replaced — so incremental Claude extractions later can
overwrite specific fields without wiping this seed.

Usage:  python pipeline/scripts/seed_curated_data.py [--dry-run] [--tickers SCOM KCB]
Env:    FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

FINANCIALS_JSON = PIPELINE_ROOT / "config" / "financials.json"
FUNDAMENTALS_JSON = PIPELINE_ROOT / "config" / "fundamentals.json"


def strip_nr(safe_ticker: str) -> str:
    return safe_ticker[:-3] if safe_ticker.endswith("_NR") else safe_ticker


def derive_shares_from_financials(entry: dict) -> tuple[float | None, dict | None]:
    """shares_outstanding_mn ≈ net_income_kes_mn / eps for the most recent
    annual row where both are positive. Returns (shares, derived_from_dict)."""
    annuals = sorted(entry.get("annual", []), key=lambda r: r.get("period_end", "") or "", reverse=True)
    for row in annuals:
        eps = row.get("eps")
        ni = row.get("net_income_kes_mn")
        if eps and ni and eps > 0 and ni > 0:
            shares_mn = round(ni / eps, 1)
            return shares_mn, {
                "period": row.get("period"),
                "period_end": row.get("period_end"),
                "net_income_kes_mn": ni,
                "eps": eps,
            }
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tickers", nargs="*")
    args = parser.parse_args()

    financials_raw = json.loads(FINANCIALS_JSON.read_text(encoding="utf-8"))
    fundamentals_raw = json.loads(FUNDAMENTALS_JSON.read_text(encoding="utf-8"))
    fundamentals_curated = {k: v for k, v in fundamentals_raw.items() if not k.startswith("_")}

    from scripts.firebase_client import get_firestore
    db = get_firestore()

    # ── financials/{bare_ticker} ────────────────────────────────────────────
    print("=== Seeding financials/{ticker} ===")
    fin_written = 0
    for safe_ticker, payload in sorted(financials_raw.items()):
        bare = strip_nr(safe_ticker)
        if args.tickers and bare not in {t.upper() for t in args.tickers}:
            continue

        # Sort arrays so newest is first (matches scraper convention)
        payload["annual"] = sorted(
            payload.get("annual", []),
            key=lambda r: r.get("period_end", "") or "",
            reverse=True,
        )
        payload["dividends"] = sorted(
            payload.get("dividends", []),
            key=lambda d: d.get("announcement_date", "") or "",
            reverse=True,
        )
        payload["_source"] = "pipeline/config/financials.json (curated)"
        payload["_seeded_at"] = datetime.now(timezone.utc).isoformat()

        latest = payload["annual"][0] if payload["annual"] else {}
        print(
            f"  {bare:<6} annual={len(payload['annual']):>2}  "
            f"dividends={len(payload['dividends']):>2}  "
            f"latest={latest.get('period','?')}  eps={latest.get('eps')}"
        )
        if not args.dry_run:
            # merge=True so the .announcements + .corporate_actions arrays
            # written by the disclosure scraper survive this seed.
            db.collection("financials").document(bare).set(payload, merge=True)
            fin_written += 1

    # ── fundamentals/{bare_ticker} ──────────────────────────────────────────
    print("\n=== Seeding fundamentals/{ticker} ===")
    fund_written = 0
    # Union of curated set + tickers we can derive from financials
    all_bare = {strip_nr(k) for k in financials_raw.keys()} | set(fundamentals_curated.keys())

    for bare in sorted(all_bare):
        if args.tickers and bare not in {t.upper() for t in args.tickers}:
            continue

        curated = fundamentals_curated.get(bare)
        if curated:
            entry = {
                "ticker": bare,
                "shares_outstanding_mn": curated["shares_outstanding_mn"],
                "as_of": curated.get("as_of"),
                "source": curated.get("source"),
                "source_url": curated.get("source_url"),
                "confidence": curated.get("confidence", "high"),
                "method": curated.get("method", "curated"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            method = "curated"
        else:
            # Back-derive from financials.json
            fin_entry = financials_raw.get(f"{bare}_NR") or financials_raw.get(bare)
            if not fin_entry:
                continue
            shares_mn, derived_from = derive_shares_from_financials(fin_entry)
            if shares_mn is None:
                continue
            entry = {
                "ticker": bare,
                "shares_outstanding_mn": shares_mn,
                "as_of": derived_from["period_end"],
                "source": f"derived from audited {derived_from['period']} net income ÷ EPS",
                "source_url": None,
                "derived_from": derived_from,
                "confidence": "medium",
                "method": "derived",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            method = "derived"

        print(f"  {bare:<6} shares={entry['shares_outstanding_mn']:>12,.1f}M  ({method})")
        if not args.dry_run:
            db.collection("fundamentals").document(bare).set(entry, merge=True)
            fund_written += 1

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n=== Done === {verb} {fin_written} financials, {fund_written} fundamentals")


if __name__ == "__main__":
    main()
