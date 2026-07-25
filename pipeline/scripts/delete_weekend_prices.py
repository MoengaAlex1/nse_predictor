"""
One-shot cleanup: delete erroneously scraped prices for a given date.

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \
    python pipeline/scripts/delete_weekend_prices.py --date 2026-07-25

Removes:
  - RTDB: /prices/{ticker}/{date} for every ticker
  - Firestore: clears intraday_today + intraday_date on companies where
    intraday_date == date
"""
import argparse
import logging
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from pipeline.scripts.firebase_client import get_firestore, get_rtdb  # noqa: E402
from pipeline.config import load_companies  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def delete_rtdb_prices(root_ref, date_str: str, companies: list[dict]) -> None:
    deleted = 0
    for co in companies:
        ticker = co["ticker"].replace(".", "_")
        ref = root_ref.child(f"prices/{ticker}/{date_str}")
        if ref.get() is not None:
            ref.delete()
            log.info("RTDB: deleted prices/%s/%s", ticker, date_str)
            deleted += 1
    log.info("RTDB: removed %d/%d ticker entries for %s", deleted, len(companies), date_str)


def clear_firestore_intraday(db, date_str: str, companies: list[dict]) -> None:
    cleared = 0
    for co in companies:
        doc_id = co["short"]
        ref = db.collection("companies").document(doc_id)
        snap = ref.get()
        if not snap.exists:
            continue
        data = snap.to_dict() or {}
        if data.get("intraday_date") == date_str:
            ref.update({"intraday_today": [], "intraday_date": None})
            log.info("Firestore: cleared intraday for %s (was %s)", doc_id, date_str)
            cleared += 1
    log.info("Firestore: cleared intraday on %d/%d companies for %s", cleared, len(companies), date_str)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD date to purge")
    parser.add_argument("--rtdb-only",      action="store_true")
    parser.add_argument("--firestore-only", action="store_true")
    args = parser.parse_args()

    companies = load_companies()
    log.info("Purging %s across %d tickers", args.date, len(companies))

    if not args.firestore_only:
        root_ref = get_rtdb()
        delete_rtdb_prices(root_ref, args.date, companies)

    if not args.rtdb_only:
        db = get_firestore()
        clear_firestore_intraday(db, args.date, companies)

    log.info("Done.")


if __name__ == "__main__":
    main()
