"""
One-time seed script using Firebase CLI OAuth2 credentials via Firestore REST API.
Bypasses gRPC (which rejects user tokens) in favour of HTTP REST.
"""

import json
import sys
from pathlib import Path

import requests

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.merge_and_seed_extracted import load_existing, load_extracted, merge_records

PROJECT_ID = "nse-market-dashboard"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    "/databases/(default)/documents"
)


# ---------------------------------------------------------------------------
# Firestore REST wire-format serialisation
# ---------------------------------------------------------------------------

def _to_firestore(value) -> dict:
    if value is None:
        return {"nullValue": None}
    if isinstance(value, bool):
        return {"booleanValue": value}
    if isinstance(value, int):
        return {"integerValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, str):
        return {"stringValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_to_firestore(v) for v in value]}}
    if isinstance(value, dict):
        return {"mapValue": {"fields": {k: _to_firestore(v) for k, v in value.items()}}}
    return {"stringValue": str(value)}


def _doc_body(data: dict) -> dict:
    return {"fields": {k: _to_firestore(v) for k, v in data.items()}}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def get_access_token() -> str:
    config = Path.home() / ".config" / "configstore" / "firebase-tools.json"
    data = json.loads(config.read_text(encoding="utf-8"))
    token = data["tokens"]["access_token"]
    if not token:
        raise RuntimeError("No access_token in firebase-tools.json. Run: firebase login")
    return token


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def seed_ticker(token: str, ticker: str, annual: list, existing_doc: dict) -> None:
    doc = {
        "annual": annual,
        "dividends": existing_doc.get("dividends", []),
        "corporate_actions": existing_doc.get("corporate_actions", []),
    }
    url = f"{FIRESTORE_BASE}/financials/{ticker}"
    resp = requests.patch(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=_doc_body(doc),
        timeout=30,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--tickers", nargs="*")
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
        token = get_access_token()
        print(f"Using Firebase CLI access token ({token[:20]}...)")

    seeded = 0
    errors = []
    for ticker in sorted(target_tickers):
        existing_doc = existing_all.get(ticker, {})
        existing_annual = existing_doc.get("annual", [])
        extracted_records = extracted_all.get(ticker, [])

        merged = merge_records(existing_annual, extracted_records)

        annual_only = [
            r for r in merged
            if r.get("period_type", "annual") == "annual"
            and any(r.get(f) is not None for f in ["revenue_kes_mn", "net_income_kes_mn", "eps"])
        ]
        interim = [
            r for r in merged
            if r.get("period_type") == "interim"
            and r.get("eps") is not None
        ]
        final = sorted(
            annual_only + interim,
            key=lambda r: r.get("period_end") or "",
            reverse=True,
        )

        extracted_count = len([r for r in extracted_records if r.get("period_end")])
        print(f"\n[{ticker}] existing={len(existing_annual)} extracted={extracted_count} merged={len(final)}")
        for r in final[:3]:
            print(
                f"  {r.get('period', '?'):20} "
                f"rev={str(r.get('revenue_kes_mn', '-')):>12} "
                f"pat={str(r.get('net_income_kes_mn', '-')):>10} "
                f"eps={r.get('eps', '-')}"
            )

        if not args.dry_run and final:
            try:
                seed_ticker(token, ticker, final, existing_doc)
                seeded += 1
                print(f"  -> seeded {len(final)} records")
            except requests.HTTPError as exc:
                errors.append((ticker, str(exc)))
                print(f"  -> ERROR: {exc}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would seed {len(target_tickers)} tickers")
    else:
        print(f"\n=== Done === Seeded {seeded}/{len(target_tickers)} tickers")
        if errors:
            print("Errors:")
            for t, e in errors:
                print(f"  {t}: {e}")


if __name__ == "__main__":
    main()
