"""
bulk_patch_from_archives.py

Reads one or more NSE annual archive CSVs
(NSE_data_all_stocks_YYYY.csv or NSE_patch_*.csv) and:

  1. For each (company, date) pair in the archive:
     - Adds the row if missing from the cleaned CSV
     - Corrects the Close price if it differs from the archive
  2. Applies decimal corrections for known corrupt companies:
     - HAFR: from 2026-01-01, divide by 100 if price > 10
     - EVRD: from 2026-02-13, divide by 100 if price > 10
  3. Reports every change made

Usage:
    python pipeline/scripts/bulk_patch_from_archives.py
        --archive-dir C:/Users/moeng/Downloads/archive
        [--years 2025 2026]
        [--tickers HAFR EVRD KURV SCOM]
        [--dry-run]

    # Single file:
    python pipeline/scripts/bulk_patch_from_archives.py
        --archive C:/path/to/NSE_data_all_stocks_2026.csv
        [--dry-run]
"""

import argparse
import csv
import logging
import sys
from datetime import datetime
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
DATA_CLEANED = PIPELINE_ROOT.parent / "data" / "cleaned"
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FIELDNAMES = ["Date", "Open", "High", "Low", "Close", "Volume", "Is_Stale", "Ticker"]

# Companies where price > threshold at given cutoff means 100x inflation
INFLATION_RULES: dict[str, tuple[str, float]] = {
    "EVRD": ("2026-01-01", 10.0),
    "HAFR": ("2026-01-01", 10.0),
}


def _parse_date(raw: str) -> str:
    """Convert 7/17/2026, 17-Jul-26, 2-Jan-25, 2026-07-17 → 2026-07-17."""
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y", "%-d-%b-%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Unrecognised date: {raw!r}")


def _safe_float(v: str | None) -> float:
    try:
        return float(str(v or "").strip().replace(",", "").rstrip("%"))
    except (ValueError, TypeError):
        return 0.0


def _corrected_price(ticker: str, date_iso: str, price: float) -> float:
    """Apply 100x inflation correction if rule matches."""
    rule = INFLATION_RULES.get(ticker)
    if rule and date_iso >= rule[0] and price > rule[1]:
        return round(price / 100, 4)
    return price


def load_archive_multidate(path: Path, ticker_filter: set[str] | None = None) -> dict[str, list[dict]]:
    """Return {code: [row_dict, ...]} preserving all dates."""
    result: dict[str, list[dict]] = {}
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row.get("Code", "").strip()
                if not code:
                    continue
                if ticker_filter and code not in ticker_filter:
                    continue
                try:
                    row["_date_iso"] = _parse_date(row.get("Date", ""))
                except ValueError:
                    continue
                adj_raw = (row.get("Adjusted Price") or row.get("Day Price") or "").strip()
                adj = _safe_float(adj_raw)
                if adj <= 0:
                    continue
                result.setdefault(code, []).append(row)
    except Exception as e:
        log.warning("Failed to read %s: %s", path, e)
    return result


def load_cleaned(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_cleaned(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def build_new_row(date_iso: str, archive_row: dict, ticker: str) -> dict:
    adj = _safe_float(archive_row.get("Adjusted Price") or archive_row.get("Day Price", "0"))
    adj = _corrected_price(ticker, date_iso, adj)
    day_high = _corrected_price(ticker, date_iso, _safe_float(archive_row.get("Day High", "0"))) or adj
    day_low = _corrected_price(ticker, date_iso, _safe_float(archive_row.get("Day Low", "0"))) or adj
    volume = _safe_float(archive_row.get("Volume", "0"))
    return {
        "Date": date_iso,
        "Open": adj,
        "High": day_high,
        "Low": day_low,
        "Close": adj,
        "Volume": int(volume),
        "Is_Stale": 0,
        "Ticker": ticker,
    }


def fix_existing_inflation(ticker: str, rows: list[dict], dry_run: bool) -> int:
    """Divide Close/Open/High/Low by 100 for rows matching inflation rule."""
    rule = INFLATION_RULES.get(ticker)
    if not rule:
        return 0
    cutoff, threshold = rule
    fixed = 0
    for r in rows:
        if r.get("Date", "") >= cutoff and str(r.get("Is_Stale", "0")) == "0":
            p = _safe_float(r["Close"])
            if p > threshold:
                if not dry_run:
                    r["Close"] = round(p / 100, 4)
                    r["Open"] = round(_safe_float(r["Open"]) / 100, 4)
                    r["High"] = round(_safe_float(r["High"]) / 100, 4)
                    r["Low"] = round(_safe_float(r["Low"]) / 100, 4)
                fixed += 1
    return fixed


def patch_company_multidate(
    safe: str,
    ticker: str,
    archive_rows: list[dict],
    dry_run: bool,
) -> dict:
    csv_path = DATA_CLEANED / f"{safe}_cleaned.csv"
    if not csv_path.exists():
        return {"safe": safe, "status": "no_csv"}

    rows = load_cleaned(csv_path)
    changed = False
    stats = {"safe": safe, "inflation_fixed": 0, "added": 0, "corrected": 0, "already_correct": 0}

    # Step 1: Fix existing inflation in the cleaned CSV
    inflation_fixed = fix_existing_inflation(ticker, rows, dry_run)
    if inflation_fixed:
        stats["inflation_fixed"] = inflation_fixed
        changed = True
        log.info("%s: fixed %d inflation rows in existing CSV", safe, inflation_fixed)

    # Step 2: Build a date index of existing rows
    date_index: dict[str, int] = {r.get("Date", "")[:10]: i for i, r in enumerate(rows)}

    # Step 3: Process each archive date
    for arc_row in sorted(archive_rows, key=lambda x: x["_date_iso"]):
        date_iso = arc_row["_date_iso"]
        adj_raw = (arc_row.get("Adjusted Price") or arc_row.get("Day Price") or "").strip()
        archive_price_raw = _safe_float(adj_raw)
        archive_price = _corrected_price(ticker, date_iso, archive_price_raw)

        if archive_price <= 0:
            continue

        existing_idx = date_index.get(date_iso)
        if existing_idx is None:
            new_row = build_new_row(date_iso, arc_row, ticker)
            insert_at = len(rows)
            for i, r in enumerate(rows):
                if r.get("Date", "") > date_iso:
                    insert_at = i
                    break
            rows.insert(insert_at, new_row)
            date_index = {r.get("Date", "")[:10]: i for i, r in enumerate(rows)}
            changed = True
            stats["added"] += 1
            log.info("%s: added %s @ %.4f", safe, date_iso, archive_price)
        else:
            stored_close = _safe_float(rows[existing_idx]["Close"])
            if abs(stored_close - archive_price) > 0.001:
                if not dry_run:
                    dh = _corrected_price(ticker, date_iso, _safe_float(arc_row.get("Day High", "0")))
                    dl = _corrected_price(ticker, date_iso, _safe_float(arc_row.get("Day Low", "0")))
                    rows[existing_idx]["Close"] = archive_price
                    rows[existing_idx]["Open"] = archive_price
                    rows[existing_idx]["High"] = dh or archive_price
                    rows[existing_idx]["Low"] = dl or archive_price
                    rows[existing_idx]["Is_Stale"] = 0
                changed = True
                stats["corrected"] += 1
                log.info("%s: corrected %s %.4f -> %.4f", safe, date_iso, stored_close, archive_price)
            else:
                stats["already_correct"] += 1

    if changed and not dry_run:
        save_cleaned(csv_path, rows)
        stats["rows"] = len(rows)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--archive", help="Single archive CSV file")
    group.add_argument("--archive-dir", help="Directory containing NSE_data_all_stocks_YYYY.csv files")
    parser.add_argument("--years", nargs="+", type=int, help="Year filter when using --archive-dir")
    parser.add_argument("--tickers", nargs="+", help="Ticker code filter (e.g. HAFR EVRD KURV)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ticker_filter = set(args.tickers) if args.tickers else None

    if args.archive:
        archive_paths = [Path(args.archive)]
    else:
        archive_dir = Path(args.archive_dir)
        archive_paths = sorted(archive_dir.glob("NSE_data_all_stocks_*.csv"))
        if args.years:
            archive_paths = [p for p in archive_paths if any(str(y) in p.name for y in args.years)]

    if not archive_paths:
        log.error("No archive files found")
        sys.exit(1)

    log.info("Processing %d archive file(s)", len(archive_paths))

    # Merge all archives into one code → [rows] dict
    merged: dict[str, list[dict]] = {}
    for path in archive_paths:
        log.info("Loading %s", path.name)
        data = load_archive_multidate(path, ticker_filter)
        for code, rows in data.items():
            merged.setdefault(code, []).extend(rows)

    companies = load_companies()
    code_map = {c["ticker"].split(".")[0]: c for c in companies}

    total_added = total_corrected = total_inflation = 0
    changed_tickers: list[str] = []
    skipped_codes: list[str] = []

    for code, arc_rows in sorted(merged.items()):
        company = code_map.get(code)
        if not company:
            skipped_codes.append(code)
            continue

        safe = company["ticker"].replace(".", "_")
        ticker = code

        stats = patch_company_multidate(safe, ticker, arc_rows, args.dry_run)

        n_added = stats.get("added", 0)
        n_corrected = stats.get("corrected", 0)
        n_inflation = stats.get("inflation_fixed", 0)
        total_added += n_added
        total_corrected += n_corrected
        total_inflation += n_inflation

        if n_added or n_corrected or n_inflation:
            changed_tickers.append(safe)
            print(
                f"{safe}: added={n_added}, corrected={n_corrected}, "
                f"inflation_fixed={n_inflation}, unchanged={stats.get('already_correct', 0)}"
            )

    print("\n=== Bulk Patch Summary ===")
    if args.dry_run:
        print("DRY RUN — no files written")
    print(f"Changed: {len(changed_tickers)} companies")
    print(f"Total rows added: {total_added} | corrected: {total_corrected} | inflation fixed: {total_inflation}")
    if skipped_codes:
        print(f"Skipped (not in system): {', '.join(sorted(set(skipped_codes)))}")


if __name__ == "__main__":
    main()
