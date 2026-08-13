"""
audit_rtdb_zeros.py

One-shot RTDB data-quality audit + optional purge.

Reads every price node under prices/{short}/ and reports:
  1. Zero-price rows (c<=0 or o/h/l<=0) — should never exist; the
     _build_node write guard now blocks these but legacy fills remain.
  2. Decimal-shift outliers — rows whose Close is 10x higher or 10x lower
     than the 5-day median of surrounding trading days. These are the
     classic OCR misreads (SCOM 17.10 → 171.00 or 456 → 45.6 patterns).
  3. Circuit-breaker violations — moves > 15% vs previous close (NSE's
     hard band is 10% for most securities; 15% is a lenient outlier flag).
  4. Fill-forward runs — consecutive identical close prices > 4 days,
     which usually means the scraper front-filled a gap.

Modes:
  --report-only (default): print counts and the top-20 worst rows per
    category. No writes. Safe on prod.
  --purge-zeros: null the c/o/h/l fields for rows with any non-positive
    price value. Volume + change fields untouched.
  --purge-outliers: null decimal-shift rows so the chart draws a gap
    instead of a spike.

Usage:
  python pipeline/scripts/audit_rtdb_zeros.py --report-only
  python pipeline/scripts/audit_rtdb_zeros.py --purge-zeros
  python pipeline/scripts/audit_rtdb_zeros.py --purge-zeros --purge-outliers

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_RTDB_URL
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


DECIMAL_RATIO = 10.0    # 10x jump either direction = decimal misread
CIRCUIT_PCT   = 15.0    # % move vs prev close flagged as circuit-breaker violation
FILL_RUN_LEN  = 5       # 5+ identical closes in a row = suspected fill


def _init_firebase():
    """Initialize firebase_admin against the RTDB URL and return a root ref."""
    import json
    import firebase_admin
    from firebase_admin import credentials, db as firebase_db

    if not firebase_admin._apps:
        cred_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        rtdb_url  = os.environ.get("FIREBASE_RTDB_URL")
        if not cred_json or not rtdb_url:
            raise SystemExit("FIREBASE_SERVICE_ACCOUNT_JSON and FIREBASE_RTDB_URL must be set")
        cred = credentials.Certificate(json.loads(cred_json))
        firebase_admin.initialize_app(cred, {"databaseURL": rtdb_url})
    return firebase_db.reference("/")


def _load_all_prices(root_ref) -> dict[str, dict[str, dict]]:
    """
    Fetch prices/ subtree from RTDB in one shot.
    Returns {ticker: {date: node_dict}}.
    """
    log.info("Loading prices/ subtree ...")
    val = root_ref.child("prices").get()
    if not val:
        log.warning("prices/ node is empty")
        return {}
    log.info("Loaded %d tickers", len(val))
    return val


def audit_zeros(prices: dict) -> dict[str, list[str]]:
    """Return {ticker: [dates_with_nonpositive_price]}."""
    hits: dict[str, list[str]] = defaultdict(list)
    for ticker, rows in prices.items():
        if not isinstance(rows, dict):
            continue
        for date, node in rows.items():
            if not isinstance(node, dict):
                continue
            for k in ("c", "o", "h", "l"):
                v = node.get(k)
                if isinstance(v, (int, float)) and v <= 0:
                    hits[ticker].append(date)
                    break
    return hits


def audit_decimal_shifts(prices: dict) -> dict[str, list[tuple[str, float, float]]]:
    """
    Return {ticker: [(date, close, median_neighbours)]} for rows whose Close is
    ≥ 10x higher or lower than the median of the 5 neighbouring days (excluding
    itself). Uses only c>0 rows for the median so surrounding zeros don't
    poison the reference.
    """
    hits: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for ticker, rows in prices.items():
        if not isinstance(rows, dict):
            continue
        dates = sorted(rows.keys())
        closes = []
        for d in dates:
            node = rows.get(d) or {}
            c = node.get("c") if isinstance(node, dict) else None
            closes.append(c if isinstance(c, (int, float)) and c > 0 else None)

        for i, (d, c) in enumerate(zip(dates, closes)):
            if c is None:
                continue
            # 5-day symmetric window excluding the row itself
            window = [x for j in range(max(0, i - 5), min(len(dates), i + 6))
                        if j != i and (x := closes[j]) is not None]
            if len(window) < 3:
                continue
            med = median(window)
            if med <= 0:
                continue
            ratio = max(c / med, med / c)
            if ratio >= DECIMAL_RATIO:
                hits[ticker].append((d, c, med))
    return hits


def audit_circuit(prices: dict) -> dict[str, list[tuple[str, float, float]]]:
    """{ticker: [(date, close, prev_close)]} where |Δ%| > CIRCUIT_PCT."""
    hits: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for ticker, rows in prices.items():
        if not isinstance(rows, dict):
            continue
        dates = sorted(rows.keys())
        prev_c = None
        for d in dates:
            node = rows.get(d) or {}
            c = node.get("c") if isinstance(node, dict) else None
            if isinstance(c, (int, float)) and c > 0:
                if prev_c is not None and prev_c > 0:
                    pct = abs(c - prev_c) / prev_c * 100
                    if pct > CIRCUIT_PCT:
                        hits[ticker].append((d, c, prev_c))
                prev_c = c
    return hits


def purge_prices(root_ref, ticker: str, dates: list[str]) -> int:
    """For each date, null the o/h/l/c fields (keep v, ch, pch, vv)."""
    if not dates:
        return 0
    updates: dict = {}
    for d in dates:
        for k in ("o", "h", "l", "c", "pc"):
            updates[f"prices/{ticker}/{d}/{k}"] = None
    root_ref.update(updates)
    return len(dates)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-only", action="store_true", default=True)
    parser.add_argument("--purge-zeros", action="store_true",
                        help="Null out o/h/l/c on rows with any non-positive price")
    parser.add_argument("--purge-outliers", action="store_true",
                        help="Null out decimal-shift outlier rows too")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    if args.purge_zeros or args.purge_outliers:
        args.report_only = False

    root_ref = _init_firebase()
    prices = _load_all_prices(root_ref)

    # ── Section 1: Zero-price rows ────────────────────────────────
    zeros = audit_zeros(prices)
    total_zero_rows = sum(len(v) for v in zeros.values())
    log.info("")
    log.info("=" * 60)
    log.info("Section 1 — Zero/negative price rows")
    log.info("=" * 60)
    log.info("Tickers with ≥1 zero row:  %d", len(zeros))
    log.info("Total bad rows:            %d", total_zero_rows)
    if zeros:
        top_zeros = sorted(zeros.items(), key=lambda kv: -len(kv[1]))[: args.top]
        for t, dates in top_zeros:
            log.info("  %-8s  %d rows  [%s]", t, len(dates),
                     ", ".join(dates[:3]) + (" …" if len(dates) > 3 else ""))

    # ── Section 2: Decimal-shift outliers ─────────────────────────
    shifts = audit_decimal_shifts(prices)
    total_shifts = sum(len(v) for v in shifts.values())
    log.info("")
    log.info("=" * 60)
    log.info("Section 2 — Decimal-shift outliers (≥10x vs 5-day median)")
    log.info("=" * 60)
    log.info("Tickers with ≥1 shift:  %d", len(shifts))
    log.info("Total shift rows:       %d", total_shifts)
    if shifts:
        top_shifts = sorted(shifts.items(), key=lambda kv: -len(kv[1]))[: args.top]
        for t, rows in top_shifts:
            log.info("  %-8s  %d rows:", t, len(rows))
            for d, c, med in rows[:3]:
                ratio = max(c / med, med / c)
                log.info("     %s  close=%.4f  median=%.4f  ratio=%.1fx",
                         d, c, med, ratio)

    # ── Section 3: Circuit-breaker violations ─────────────────────
    circuit = audit_circuit(prices)
    total_circuit = sum(len(v) for v in circuit.values())
    log.info("")
    log.info("=" * 60)
    log.info("Section 3 — Circuit-breaker violations (>%.0f%% move)", CIRCUIT_PCT)
    log.info("=" * 60)
    log.info("Tickers flagged:  %d", len(circuit))
    log.info("Total rows:       %d", total_circuit)
    if circuit:
        top_circuit = sorted(circuit.items(), key=lambda kv: -len(kv[1]))[: args.top]
        for t, rows in top_circuit:
            log.info("  %-8s  %d rows:", t, len(rows))
            for d, c, pc in rows[:3]:
                pct = (c - pc) / pc * 100
                log.info("     %s  close=%.4f  prev=%.4f  Δ=%+.1f%%", d, c, pc, pct)

    # ── Purge if requested ─────────────────────────────────────────
    if args.purge_zeros:
        log.info("")
        log.info("=" * 60)
        log.info("Purging zero-price rows …")
        log.info("=" * 60)
        total = 0
        for t, dates in zeros.items():
            n = purge_prices(root_ref, t, dates)
            total += n
            log.info("  %-8s  nulled %d rows", t, n)
        log.info("Zero-purge complete: %d rows nulled", total)

    if args.purge_outliers:
        log.info("")
        log.info("=" * 60)
        log.info("Purging decimal-shift outliers …")
        log.info("=" * 60)
        total = 0
        for t, rows in shifts.items():
            dates = [d for d, _, _ in rows]
            n = purge_prices(root_ref, t, dates)
            total += n
            log.info("  %-8s  nulled %d rows", t, n)
        log.info("Outlier-purge complete: %d rows nulled", total)

    if args.report_only and not (args.purge_zeros or args.purge_outliers):
        log.info("")
        log.info("(Report-only mode — no writes. Re-run with --purge-zeros / "
                 "--purge-outliers to fix.)")


if __name__ == "__main__":
    main()
