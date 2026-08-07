"""
archive_reference.py

Loader for the downloaded NSE all-stocks archive — the authoritative reference
used to maker-check prices.

This replaces guesswork. Earlier corrections leaned on price bands read off
chart axes by eye, which were approximate and unverifiable. The archive gives
the exchange's own printed close for a specific ticker on a specific date, so a
correction becomes a lookup rather than an inference.

FILE SHAPE
  One CSV per year: NSE_data_all_stocks_<YEAR>.csv
  Columns: Date, Code, Name, 12m Low, 12m High, Day Low, Day High,
           Day Price, Previous, Change, Change%, Volume, Adjust[ed Price]

  "Day Price" is the close. "Code" is the ticker.

INCONSISTENCIES HANDLED
  Header case      2007-2023 use DATE/CODE, 2024-2025 use Date/Code
  BOM              2007 and 2025 are UTF-8 with a byte-order mark
  Last column      "Adjust" before 2024, "Adjusted Price" after
  Date format      2007 uses M/D/YYYY, later years use D-Mon-YY
  Missing values   "-" means no trade that day, not zero
  Thousands commas Volume is written like "7,800"
  Index rows       Rows whose Code starts with "^" are indices, not equities

COVERAGE
  The archive is complete years 2007 through 2025. It does NOT cover 2026, so
  anything in the current year cannot be maker-checked against it and must not
  be corrected from it.
"""

from __future__ import annotations

import csv
import datetime
import glob
import os
import re
from functools import lru_cache

DEFAULT_ARCHIVE = os.path.expanduser("~/Documents/archive")

# Ordered by how common they are across the files.
_DATE_FORMATS = ("%d-%b-%y", "%m/%d/%Y", "%d-%B-%y", "%Y-%m-%d", "%d/%m/%Y")


def _parse_date(raw: str) -> datetime.date | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_number(raw: str) -> float | None:
    """'-' means no trade. '7,800' is 7800. Anything unparseable is None."""
    raw = (raw or "").strip().replace(",", "").replace("%", "")
    if raw in ("", "-", "N/A", "NA"):
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    return v


def _normalise_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map a lowercased logical name to the actual column name in this file."""
    out = {}
    for k in fieldnames or []:
        key = k.strip().lstrip("﻿").lower()
        out[key] = k
    return out


def iter_archive(archive_dir: str = DEFAULT_ARCHIVE):
    """Yield (date, code, close, prev, low, high, volume) for every equity row."""
    for path in sorted(glob.glob(os.path.join(archive_dir, "NSE_data_all_stocks_*.csv"))):
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rdr = csv.DictReader(fh)
            cols = _normalise_headers(rdr.fieldnames)
            c_date = cols.get("date")
            c_code = cols.get("code")
            if not c_date or not c_code:
                continue
            for row in rdr:
                code = (row.get(c_code) or "").strip().upper()
                if not code or code.startswith("^"):
                    continue                      # index, not an equity
                d = _parse_date(row.get(c_date, ""))
                if d is None:
                    continue
                yield (
                    d,
                    code,
                    _parse_number(row.get(cols.get("day price", ""), "")),
                    _parse_number(row.get(cols.get("previous", ""), "")),
                    _parse_number(row.get(cols.get("day low", ""), "")),
                    _parse_number(row.get(cols.get("day high", ""), "")),
                    _parse_number(row.get(cols.get("volume", ""), "")),
                )


@lru_cache(maxsize=1)
def load_reference(archive_dir: str = DEFAULT_ARCHIVE) -> dict[str, dict[str, dict]]:
    """
    {TICKER: {"YYYY-MM-DD": {"c":..., "pc":..., "l":..., "h":..., "v":...}}}

    Only rows with a usable close are kept — a row with "-" for Day Price means
    the stock did not trade, which is information the corrector must not read
    as a price.
    """
    ref: dict[str, dict[str, dict]] = {}
    for d, code, close, prev, low, high, vol in iter_archive(archive_dir):
        if close is None:
            continue
        ref.setdefault(code, {})[d.isoformat()] = {
            "c": close, "pc": prev, "l": low, "h": high, "v": vol,
        }
    return ref


def coverage(archive_dir: str = DEFAULT_ARCHIVE) -> dict:
    ref = load_reference(archive_dir)
    all_dates = [d for t in ref for d in ref[t]]
    return {
        "tickers": len(ref),
        "rows": sum(len(v) for v in ref.values()),
        "first": min(all_dates) if all_dates else None,
        "last": max(all_dates) if all_dates else None,
    }
