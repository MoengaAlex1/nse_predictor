"""
apply_archive_corrections.py

Repairs RTDB prices by copying the NSE archive's published figures. Dry-run by
default; writes only when --apply is passed, and only after taking a backup.

WHY COPY RATHER THAN SCALE
--------------------------
An earlier plan was to multiply corrupt values by a power of ten. The archive
shows that is wrong:

    SMER 2020-10-14   RTDB 0.36   archive 3.50

0.36 x 10 is 3.60, not 3.50. Scaling would swap one wrong number for another.
Every field is therefore copied from the archive, never derived from the value
being replaced.

Copying also repairs a second defect in the same pass. Around 30% of sampled
mismatches are not decimal shifts but transposed dates - identical (close,
volume) rows filed under swapped days, because the 2007-2009 archive files are
M/D/YYYY and the historical import read them as D/M. Writing the archive's
value for each date fixes both defects at once.

WHAT IT REFUSES TO DO
  - Touch a date the archive does not cover. Coverage ends 2025-10-31, so the
    November 2025 SMER corruption is out of scope here and is left alone.
  - Touch a date where the archive has no close ("-" means the stock did not
    trade; reading that as a price would invent one).
  - Invent fields. Where the archive lacks a value the existing one is kept.
  - Write anything at all without --apply.

DERIVED FIELDS
  ch and pch are recomputed from the corrected c and pc rather than copied,
  because c - pc == ch holds on 100.0% of rows: they are derived in this
  dataset, and leaving stale values would contradict the corrected prices.

USAGE
  python pipeline/scripts/apply_archive_corrections.py --ticker SMER
  python pipeline/scripts/apply_archive_corrections.py --ticker SMER --diff out.csv
  python pipeline/scripts/apply_archive_corrections.py --ticker SMER --apply
  python pipeline/scripts/apply_archive_corrections.py --restore backup.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

log = logging.getLogger(__name__)

# Fields copied verbatim from the archive when it has them.
COPIED = {"c": "c", "pc": "pc", "l": "l", "h": "h", "v": "v"}

# A value is treated as matching, and left alone, within this relative margin.
MATCH_TOL = 0.005


def _close_enough(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= max(0.005, abs(b) * MATCH_TOL)


def build_corrections(db: dict, ref: dict, tickers: list[str] | None = None) -> list[dict]:
    """
    Compare RTDB against the archive and return one record per date needing
    change. Nothing is written here.
    """
    out: list[dict] = []
    for ticker in sorted(db):
        if tickers and ticker not in tickers:
            continue
        node, ref_t = db[ticker], ref.get(ticker)
        if not isinstance(node, dict) or not ref_t:
            continue

        for date in sorted(node):
            row = node[date]
            a = ref_t.get(date)
            if not isinstance(row, dict) or not a:
                continue                      # outside archive coverage
            if a.get("c") is None:
                continue                      # archive says no trade that day

            changes = {}
            for rtdb_key, arch_key in COPIED.items():
                new = a.get(arch_key)
                if new is None:
                    continue                  # archive lacks it — keep existing
                if not _close_enough(row.get(rtdb_key), new):
                    changes[rtdb_key] = new

            if not changes:
                continue

            merged = {**row, **changes}
            c, pc = merged.get("c"), merged.get("pc")
            if isinstance(c, (int, float)) and isinstance(pc, (int, float)):
                # Recomputed, not copied — see module docstring.
                merged["ch"] = round(c - pc, 4)
                merged["pch"] = round((c - pc) / pc * 100, 4) if pc else 0.0

            out.append({
                "ticker": ticker, "date": date,
                "before": row, "after": merged, "changed": sorted(changes),
            })
    return out


def classify(correction: dict) -> str:
    """
    What kind of disagreement is this?

      decimal    close differs from the archive by ~10x or ~100x — the
                 corruption originally reported
      minor      close differs by less than 2x — the two stores disagree, but
                 not in a way that looks like a lost decimal point
      no_close   only volume, high, low or prev-close differ
      other      anything else

    The distinction matters because the totals are wildly different: of 115,836
    rows that differ from the archive, only 1,130 are decimal shifts. Replacing
    all of them would rebuild the history wholesale rather than fix a bug.
    """
    if "c" not in correction["changed"]:
        return "no_close"
    before = correction["before"].get("c")
    after = correction["after"].get("c")
    if not before or not after:
        return "other"
    r = after / before
    if 8 < r < 12 or 0.08 < r < 0.12 or 80 < r < 120 or 0.008 < r < 0.012:
        return "decimal"
    if 0.5 < r < 2:
        return "minor"
    return "other"


def write_diff(corrections: list[dict], path: str) -> None:
    import csv
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "date", "field", "before", "after"])
        for c in corrections:
            for f in c["changed"]:
                w.writerow([c["ticker"], c["date"], f,
                            c["before"].get(f), c["after"].get(f)])


def apply_corrections(root_ref, corrections: list[dict], backup_path: str) -> int:
    """
    Write corrected nodes to RTDB after saving the originals.

    The backup is written and flushed BEFORE any RTDB call, so an interrupted
    run always leaves a complete record of what the values were.
    """
    backup = {"corrections": [{"ticker": c["ticker"], "date": c["date"],
                               "before": c["before"]} for c in corrections]}
    with open(backup_path, "w") as fh:
        json.dump(backup, fh, indent=1)
        fh.flush()
    log.info("Backup of %d original rows written to %s", len(corrections), backup_path)

    from pipeline.scripts.firebase_rtdb import to_short_ticker
    written = 0
    for c in corrections:
        short = to_short_ticker(c["ticker"])
        root_ref.update({f"prices/{short}/{c['date']}": c["after"]})
        written += 1
    return written


def restore(root_ref, backup_path: str) -> int:
    """Put back every original row recorded in a backup file."""
    from pipeline.scripts.firebase_rtdb import to_short_ticker
    data = json.loads(Path(backup_path).read_text())
    n = 0
    for c in data["corrections"]:
        short = to_short_ticker(c["ticker"])
        root_ref.update({f"prices/{short}/{c['date']}": c["before"]})
        n += 1
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", action="append", help="Limit to this ticker (repeatable)")
    ap.add_argument("--from-file", help="Read a prices JSON dump instead of RTDB")
    ap.add_argument("--diff", help="Write a per-field CSV diff here")
    ap.add_argument("--only", choices=["decimal", "minor", "no_close", "other"],
                    action="append",
                    help="Limit to these disagreement kinds. --only decimal "
                         "targets the reported corruption without rebuilding "
                         "the whole history.")
    ap.add_argument("--apply", action="store_true", help="Actually write to RTDB")
    ap.add_argument("--backup", default="rtdb_price_backup.json")
    ap.add_argument("--restore", help="Restore originals from a backup file")
    args = ap.parse_args()

    if args.restore:
        from pipeline.scripts.firebase_client import get_rtdb
        n = restore(get_rtdb(), args.restore)
        print(f"Restored {n} rows from {args.restore}")
        return

    from pipeline.scripts.archive_reference import load_reference, coverage
    ref = load_reference()
    cov = coverage()
    print(f"Archive: {cov['tickers']} tickers, {cov['rows']:,} rows, "
          f"{cov['first']} to {cov['last']}")

    if args.from_file:
        db = json.load(open(args.from_file))
    else:
        from pipeline.scripts.firebase_client import get_rtdb
        db = get_rtdb().child("prices").get()

    corrections = build_corrections(db, ref, args.ticker)

    kinds: dict[str, int] = {}
    for c in corrections:
        k = classify(c)
        c["kind"] = k
        kinds[k] = kinds.get(k, 0) + 1
    print("\nDisagreement breakdown:")
    for k in ("decimal", "minor", "no_close", "other"):
        if kinds.get(k):
            print(f"  {k:<10}{kinds[k]:>9,}")

    if args.only:
        corrections = [c for c in corrections if c["kind"] in args.only]
        print(f"\nFiltered to {'/'.join(args.only)}: {len(corrections):,} rows")

    by_ticker: dict[str, int] = {}
    for c in corrections:
        by_ticker[c["ticker"]] = by_ticker.get(c["ticker"], 0) + 1

    print(f"\nRows needing correction: {len(corrections):,}")
    for t, n in sorted(by_ticker.items(), key=lambda x: -x[1])[:15]:
        print(f"  {t:<8}{n:>7,}")

    print(f"\n{'ticker':<8}{'date':<12}{'field':<6}{'before':>12}{'after':>12}")
    for c in corrections[:20]:
        for f in c["changed"]:
            print(f"  {c['ticker']:<8}{c['date']:<12}{f:<6}"
                  f"{str(c['before'].get(f)):>12}{str(c['after'].get(f)):>12}")

    if args.diff:
        write_diff(corrections, args.diff)
        print(f"\nFull diff written to {args.diff}")

    if not args.apply:
        print("\nDRY RUN — nothing was written. Pass --apply to write.")
        return

    from pipeline.scripts.firebase_client import get_rtdb
    n = apply_corrections(get_rtdb(), corrections, args.backup)
    print(f"\nWrote {n} corrected rows. Originals saved to {args.backup}")
    print(f"Undo with: --restore {args.backup}")


if __name__ == "__main__":
    main()
