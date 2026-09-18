"""Rebuild the RTDB `prices_latest/{TICKER}` mirror from the full `prices/` tree.

The mirror is normally maintained by :func:`firebase_rtdb.bulk_write_prices`
on every batch write. Run this script once after adding the mirror (or any
time you suspect the mirror has drifted from `prices/`) to hydrate every
ticker's `prices_latest` node from its newest date in `prices`.

Usage::

    python -m pipeline.scripts.rebuild_prices_latest [--dry-run] [--ticker SCOM] [--ticker EQTY]
"""

from __future__ import annotations

import argparse
import logging
import sys

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", action="append",
                    help="Only rebuild this ticker's mirror (repeatable). Default: all.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be written, don't touch RTDB.")
    args = ap.parse_args()

    from pipeline.scripts.firebase_client import get_rtdb

    root = get_rtdb()
    prices = root.child("prices").get() or {}

    written = 0
    skipped = 0
    for ticker in sorted(prices):
        if args.ticker and ticker not in args.ticker:
            continue
        node = prices[ticker]
        if not isinstance(node, dict) or not node:
            skipped += 1
            continue
        # Dates are ISO strings so max() on the keys is chronological.
        latest_date = max(node.keys())
        latest_row = node[latest_date]
        if not isinstance(latest_row, dict):
            skipped += 1
            continue

        payload = {"date": latest_date, **latest_row}
        if args.dry_run:
            log.info("[dry-run] %s -> %s c=%s pch=%s",
                     ticker, latest_date, latest_row.get("c"), latest_row.get("pch"))
        else:
            root.update({f"prices_latest/{ticker}": payload})
            log.info("%s -> %s c=%s pch=%s",
                     ticker, latest_date, latest_row.get("c"), latest_row.get("pch"))
        written += 1

    log.info("Rebuilt %d mirror entries (%d skipped, empty/malformed)", written, skipped)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
