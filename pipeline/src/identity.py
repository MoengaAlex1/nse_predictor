"""
identity.py

Single source of truth for the per-company primary key across the whole
codebase.

The rule (2026-08 refactor):

    Firestore doc-id, RTDB path segment, and CompanyDoc.id in the
    frontend are ALL the `short` form: an all-caps alphanumeric handle
    with no dots or underscores (e.g. "SCOM", "EQTY", "KCB", "IMH").

The `ticker` field ("SCOM.NR") is a DISPLAY alias only — used in headers
and tooltips. The `csv` field ("SCOM_NR_raw.csv") is a filesystem alias
used only when reading/writing local CSVs.

Every pipeline write that lands in Firestore or RTDB must go through
`doc_id_for(company)` so a future refactor can't accidentally re-introduce
the fragmented "SCOM.NR" / "SCOM_NR" keys we spent a day cleaning up.
"""
from __future__ import annotations

import re
from typing import Mapping

# `short` matches uppercase [A-Z0-9]{1,8}. No dots, no underscores, no dashes.
_SHORT_RE = re.compile(r"^[A-Z][A-Z0-9]{0,7}$")


class InvalidCompanyKeyError(ValueError):
    """Raised when a value that should be a `short` primary key isn't."""


def is_short(candidate: str) -> bool:
    """True iff `candidate` matches the canonical short-form key."""
    return bool(candidate) and bool(_SHORT_RE.match(candidate))


def doc_id_for(company: Mapping[str, str]) -> str:
    """
    Return the canonical Firestore / RTDB primary key for `company`.

    `company` must be a companies.json-shaped dict (has `short` and
    `ticker` keys). Raises InvalidCompanyKeyError if `short` is missing
    or malformed — better to fail loud than write to a bad key.
    """
    short = company.get("short") if isinstance(company, Mapping) else None
    if not short or not is_short(short):
        ticker = company.get("ticker", "?") if isinstance(company, Mapping) else "?"
        raise InvalidCompanyKeyError(
            f"Company {ticker!r} has invalid or missing `short` key: {short!r}. "
            f"Expected uppercase alphanumeric like 'SCOM'."
        )
    return short


def short_from_display_ticker(ticker: str) -> str:
    """
    Best-effort recovery of the short form from a display ticker like
    "SCOM.NR" or a filesystem-safe form like "SCOM_NR". Used ONLY by
    the migration script when scanning legacy Firestore docs — normal
    code paths should always call `doc_id_for(company_dict)` instead.
    """
    if not ticker:
        raise InvalidCompanyKeyError("empty ticker")
    base = ticker.upper()
    # Strip .NR / _NR / .KE / _KE tail
    for suffix in (".NR", "_NR", ".KE", "_KE"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if not is_short(base):
        raise InvalidCompanyKeyError(
            f"Cannot derive short form from {ticker!r} → {base!r}"
        )
    return base
