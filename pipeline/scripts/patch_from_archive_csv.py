"""
patch_from_archive_csv.py

Reads an NSE daily-trading archive CSV (Date, Code, Name, Day Low, Day High,
Day Price, Previous, Change, Change%, Volume, Adjusted Price) and:

  1. For each company in our system that appears in the archive CSV:
     - Adds the date's row if missing from the cleaned CSV
     - Corrects the Close price if it differs from the archive's Adjusted Price
  2. For EVRD specifically: fixes the Feb-Jul 2026 100x inflation
  3. Reports every change made

Usage:
    python pipeline/scripts/patch_from_archive_csv.py
        --archive path/to/NSE_patch_2026-07-17.csv
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


def _parse_date(raw: str) -> str:
    """Convert 7/17/2026 or 2026-07-17 → 2026-07-17."""
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"Unrecognised date: {raw!r}")


def load_archive(path: Path) -> dict[str, dict]:
    """Return {code: row_dict} from the archive CSV."""
    result = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row["Code"].strip()
            result[code] = row
    return result


def _safe_float(v: str) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def load_cleaned(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_cleaned(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(rows)


def build_new_row(date_iso: str, archive_row: dict, ticker: str) -> dict:
    """Build a cleaned-CSV row from an archive CSV row."""
    adj = _safe_float(archive_row.get("Adjusted Price") or archive_row.get("Day Price", "0"))
    day_high = _safe_float(archive_row.get("Day High", "0")) or adj
    day_low = _safe_float(archive_row.get("Day Low", "0")) or adj
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


def fix_evrd_inflation(rows: list[dict], dry_run: bool) -> tuple[list[dict], int]:
    """
    EVRD prices are ~100x inflated throughout 2026.
    Divide Close/Open/High/Low by 100 for affected rows.
    """
    CUTOFF = "2026-01-01"
    fixed = 0
    for r in rows:
        if r["Date"] >= CUTOFF and r.get("Is_Stale", "0") == "0":
            p = _safe_float(r["Close"])
            if p > 10:  # current correct range is ~1-2 KES
                if not dry_run:
                    r["Close"] = round(p / 100, 4)
                    r["Open"] = round(_safe_float(r["Open"]) / 100, 4)
                    r["High"] = round(_safe_float(r["High"]) / 100, 4)
                    r["Low"] = round(_safe_float(r["Low"]) / 100, 4)
                fixed += 1
    return rows, fixed


def patch_company(
    safe: str,
    ticker: str,
    archive_row: dict,
    dry_run: bool,
) -> dict:
    csv_path = DATA_CLEANED / f"{safe}_cleaned.csv"
    if not csv_path.exists():
        return {"safe": safe, "status": "no_csv"}

    date_iso = _parse_date(archive_row["Date"])
    archive_price = _safe_float(archive_row.get("Adjusted Price") or archive_row.get("Day Price", "0"))

    rows = load_cleaned(csv_path)
    original_count = len(rows)

    changed = False
    result = {"safe": safe, "date": date_iso, "archive_price": archive_price}

    # 1. EVRD-specific: fix the Feb 2026+ 100x inflation before touching Jul 17
    inflation_fixed = 0
    if ticker == "EVRD":
        rows, inflation_fixed = fix_evrd_inflation(rows, dry_run)
        if inflation_fixed:
            changed = True
            result["evrd_inflation_fixed"] = inflation_fixed

    # 2. Find the target date row
    target_idx = next(
        (i for i, r in enumerate(rows) if r.get("Date", "")[:10] == date_iso),
        None,
    )

    if target_idx is None:
        # Date is missing — insert sorted
        new_row = build_new_row(date_iso, archive_row, ticker)
        insert_at = len(rows)
        for i, r in enumerate(rows):
            if r.get("Date", "") > date_iso:
                insert_at = i
                break
        rows.insert(insert_at, new_row)
        changed = True
        result["action"] = "added"
        result["close"] = archive_price
        log.info("%s: added %s @ %.4f", safe, date_iso, archive_price)
    else:
        stored_close = _safe_float(rows[target_idx]["Close"])
        if abs(stored_close - archive_price) > 0.001:
            result["stored_was"] = stored_close
            result["action"] = "corrected"
            result["close"] = archive_price
            if not dry_run:
                rows[target_idx]["Close"] = archive_price
                rows[target_idx]["Open"] = archive_price
                rows[target_idx]["High"] = _safe_float(archive_row.get("Day High", "0")) or archive_price
                rows[target_idx]["Low"] = _safe_float(archive_row.get("Day Low", "0")) or archive_price
                rows[target_idx]["Is_Stale"] = 0
            changed = True
            log.info("%s: corrected %s %.4f -> %.4f", safe, date_iso, stored_close, archive_price)
        else:
            result["action"] = "already_correct"

    if changed and not dry_run:
        save_cleaned(csv_path, rows)
        result["rows"] = len(rows)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, help="Path to the NSE archive CSV")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    archive = load_archive(Path(args.archive))
    companies = load_companies()

    # Build code → company lookup (ticker base without .NR)
    code_map = {c["ticker"].split(".")[0]: c for c in companies}

    changed_tickers: list[str] = []
    skipped_codes: list[str] = []

    for code, arc_row in sorted(archive.items()):
        company = code_map.get(code)
        if not company:
            skipped_codes.append(code)
            continue

        safe = company["ticker"].replace(".", "_")
        ticker = code

        res = patch_company(safe, ticker, arc_row, args.dry_run)

        if res.get("action") in ("added", "corrected") or res.get("evrd_inflation_fixed"):
            changed_tickers.append(safe)

    print("\n=== Patch Summary ===")
    if args.dry_run:
        print("DRY RUN — no files written")
    print(f"Changed: {len(changed_tickers)} companies: {', '.join(changed_tickers)}")
    print(f"Skipped (not in system): {', '.join(skipped_codes)}")


if __name__ == "__main__":
    main()
