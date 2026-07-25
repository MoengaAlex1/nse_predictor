"""
NSE Price Cleaner — detects and corrects price errors in cleaned CSVs.

Detection + fix rules (Is_Stale=0 rows only):

  1. Spike (Close ratio > SPIKE_RATIO, default 3×):
       - Today's date: cross-check NSE AJAX; fix ONLY if NSE confirms
       - Historical: mark Is_Stale=1 (hidden from RTDB), log reason
       - NEVER forward-fill, estimate, or invent a replacement price

  2. OHLC violation (Low > High, Low > min(O,C), High < max(O,C)):
       - Safe clamp: set Low = min(Low, Open, Close) and High = max(High, Open, Close)
       - This only adjusts H/L, never touches Open or Close
       - Logged but does NOT quarantine the row

  3. Invalid Close (≤ 0):
       - Quarantine (mark Is_Stale=1)

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \\
    python pipeline/scripts/nse_price_cleaner.py [--dry-run] [--ticker SCOM]
    [--year YYYY] [--push-rtdb]
"""
import argparse
import datetime
import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_CLEANED = REPO_ROOT / "data" / "cleaned"

NSE_AJAX_URL = "https://www.nse.co.ke/wp-admin/admin-ajax.php"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NSECleaner/1.0)",
    "Referer": "https://www.nse.co.ke/market-statistics/",
}

SPIKE_RATIO = 3.0      # flag day where Close ratio vs previous > 3× either direction
DECIMAL_RATIO = 10.0   # ratio > 10× = OCR decimal error, always flag (no sandwich test)
MIN_ROWS = 3           # need at least this many rows to detect spikes


@dataclass
class Anomaly:
    ticker: str
    date: datetime.date
    kind: str           # "spike", "ohlc", "invalid"
    detail: str         # human-readable description
    old_close: Optional[float] = None
    confirmed_close: Optional[float] = None  # NSE-verified replacement (today only)
    action: str = "quarantine"  # "quarantine" | "nse_fix" | "dry_run"
    source: str = "csv_analysis"


def fetch_nse_live_prices() -> dict[str, float]:
    """Fetch today's closing prices from NSE AJAX endpoint. Returns {SHORT_TICKER: price}."""
    try:
        resp = requests.post(
            NSE_AJAX_URL,
            data={"action": "get_listed_companies_data", "security": ""},
            headers=NSE_HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data if isinstance(data, list) else data.get("data", [])
        prices: dict[str, float] = {}
        for row in rows:
            code = (row.get("symbol") or row.get("code") or "").strip().upper()
            raw = row.get("close") or row.get("price") or row.get("last_price")
            if code and raw:
                try:
                    prices[code] = float(str(raw).replace(",", ""))
                except (ValueError, TypeError):
                    pass
        log.info("NSE AJAX: fetched %d live prices", len(prices))
        return prices
    except Exception as exc:
        log.warning("NSE AJAX fetch failed: %s", exc)
        return {}


def _is_fwd_fill_row(close, volume, o, h, l) -> bool:
    """True when a row is a forward-fill placeholder: V=0, OHLC all equal."""
    try:
        return float(volume) == 0 and float(o) == float(h) == float(l) == float(close)
    except (TypeError, ValueError):
        return False


def detect_spikes(df: pd.DataFrame, ticker: str) -> list[Anomaly]:
    """
    Flag Is_Stale=0 rows where Close is anomalous relative to the nearest SOLID neighbors.

    Solid = not a forward-fill (V=0, flat OHLC). Forward-fills are skipped as reference
    prices because they may chain bad data. Uses a sandwich test:
      - Find nearest solid prev and solid next for each candidate
      - Flag only when the candidate is anomalous vs prev AND the next solid price
        looks like a return to normal (within SPIKE_RATIO of prev)
    This avoids flagging legitimate "recovery" rows after a spike.
    """
    anomalies: list[Anomaly] = []
    active = df[df["Is_Stale"] == 0].sort_values("Date").reset_index(drop=True)
    n = len(active)
    if n < MIN_ROWS:
        return anomalies

    closes = [float(v) if pd.notna(v) else None for v in active["Close"].tolist()]
    dates = active["Date"].tolist()
    vols = [float(v) if pd.notna(v) else 0 for v in active.get("Volume", [0] * n).tolist()]
    opens = [float(v) if pd.notna(v) else None for v in active.get("Open", [None] * n).tolist()]
    highs = [float(v) if pd.notna(v) else None for v in active.get("High", [None] * n).tolist()]
    lows = [float(v) if pd.notna(v) else None for v in active.get("Low", [None] * n).tolist()]

    is_fwd = [
        _is_fwd_fill_row(closes[i], vols[i], opens[i], highs[i], lows[i])
        for i in range(n)
    ]

    def prev_solid(i: int) -> Optional[float]:
        for j in range(i - 1, -1, -1):
            if not is_fwd[j] and closes[j] and closes[j] > 0:
                return closes[j]
        return None

    def next_solid(i: int) -> Optional[float]:
        for j in range(i + 1, n):
            if not is_fwd[j] and closes[j] and closes[j] > 0:
                return closes[j]
        return None

    for i in range(n):
        curr = closes[i]
        if curr is None or curr <= 0 or is_fwd[i]:
            continue  # forward-fills and invalid prices handled elsewhere

        ps = prev_solid(i)
        if ps is None:
            continue

        prev_ratio = curr / ps
        is_spike_up = prev_ratio >= SPIKE_RATIO
        is_spike_dn = (1.0 / prev_ratio) >= SPIKE_RATIO

        if not (is_spike_up or is_spike_dn):
            continue  # not anomalous from previous

        ratio = prev_ratio if is_spike_up else (1.0 / prev_ratio)
        direction = "jump" if is_spike_up else "drop"
        detail = f"Close {curr:.4f} is {ratio:.1f}x {direction} from prev solid close {ps:.4f}"

        # Obvious OCR decimal errors (10x+) are always flagged — no sandwich test
        if ratio >= DECIMAL_RATIO:
            anomalies.append(Anomaly(ticker, dates[i].date(), "spike", detail, old_close=curr))
            continue

        # For 3x–10x spikes, apply sandwich test: if next solid price is also anomalous
        # relative to prev, this might be a genuine large move — skip (conservative)
        ns = next_solid(i)
        if ns is not None:
            next_vs_prev = ns / ps
            if next_vs_prev >= SPIKE_RATIO or (1.0 / next_vs_prev) >= SPIKE_RATIO:
                continue

        anomalies.append(Anomaly(ticker, dates[i].date(), "spike", detail, old_close=curr))

    return anomalies


def detect_spikes_iterative(df: pd.DataFrame, ticker: str, max_passes: int = 5) -> list[Anomaly]:
    """
    Run detect_spikes repeatedly, marking found spikes as stale between passes.
    This catches multi-day OCR runs where day N+1's bad price hides day N's spike.
    """
    all_anomalies: list[Anomaly] = []
    quarantine_dates: set[datetime.date] = set()
    working_df = df.copy()

    for _ in range(max_passes):
        if quarantine_dates and "Is_Stale" in working_df.columns:
            mask = (
                working_df["Date"].dt.date.isin(quarantine_dates)
                & (working_df["Is_Stale"] == 0)
            )
            working_df.loc[mask, "Is_Stale"] = 1

        new_anomalies = detect_spikes(working_df, ticker)
        new_dates = {a.date for a in new_anomalies} - quarantine_dates
        if not new_dates:
            break

        for a in new_anomalies:
            if a.date in new_dates:
                all_anomalies.append(a)
        quarantine_dates.update(new_dates)

    return all_anomalies


def detect_ohlc_violations(df: pd.DataFrame, ticker: str) -> list[Anomaly]:
    """
    Flag Is_Stale=0 rows with impossible OHLC relationships.
    Action is always a safe clamp of H/L — Open and Close are never changed.
    """
    anomalies: list[Anomaly] = []
    active = df[df["Is_Stale"] == 0].copy()

    for _, row in active.iterrows():
        o = row.get("Open")
        h = row.get("High")
        l = row.get("Low")
        c = row.get("Close")
        if any(pd.isna(x) for x in [o, h, l, c]):
            continue
        o, h, l, c = float(o), float(h), float(l), float(c)
        violations = []
        if l > h:
            violations.append(f"Low({l}) > High({h})")
        if l > min(o, c):
            violations.append(f"Low({l}) > min(Open({o}), Close({c}))")
        if h < max(o, c):
            violations.append(f"High({h}) < max(Open({o}), Close({c}))")
        if violations:
            detail = "; ".join(violations)
            a = Anomaly(ticker, row["Date"].date(), "ohlc", detail, old_close=c)
            a.action = "clamp_hl"  # always clamp H/L, never quarantine for OHLC
            anomalies.append(a)

    return anomalies


def detect_invalid_prices(df: pd.DataFrame, ticker: str) -> list[Anomaly]:
    """Flag Is_Stale=0 rows with Close ≤ 0."""
    anomalies: list[Anomaly] = []
    active = df[df["Is_Stale"] == 0]
    for _, row in active.iterrows():
        c = row.get("Close")
        if pd.notna(c) and float(c) <= 0:
            anomalies.append(Anomaly(
                ticker, row["Date"].date(), "invalid",
                f"Close={c} is zero or negative", old_close=float(c)
            ))
    return anomalies


def apply_nse_fix(anomaly: Anomaly, nse_prices: dict[str, float], today: datetime.date) -> bool:
    """
    If the anomaly is on today's date and NSE has a live price, set confirmed_close.
    Returns True if a fix was found.
    """
    if anomaly.date != today:
        return False
    short = anomaly.ticker.split("_")[0].upper()
    nse_price = nse_prices.get(short)
    if nse_price and nse_price > 0:
        anomaly.confirmed_close = nse_price
        anomaly.action = "nse_fix"
        anomaly.source = "nse_ajax"
        return True
    return False


def cascade_quarantine_fwd_fills(
    df: pd.DataFrame, spike_dates: set[datetime.date]
) -> set[datetime.date]:
    """
    Find forward-fill rows (V=0, flat OHLC) that immediately follow a quarantined spike date.
    These forward-fills carry the wrong price forward and must also be quarantined.
    Returns the expanded set of dates to quarantine.
    """
    expanded = set(spike_dates)
    if "Is_Stale" not in df.columns:
        return expanded

    active = df[df["Is_Stale"] == 0].sort_values("Date").reset_index(drop=True)

    def is_fwd(row) -> bool:
        return _is_fwd_fill_row(
            row.get("Close"), row.get("Volume"),
            row.get("Open"), row.get("High"), row.get("Low"),
        )

    for i, row in active.iterrows():
        d = row["Date"].date()
        if d not in expanded and is_fwd(row):
            # Check if previous non-fwd-fill date is in expanded (spike)
            prev_rows = active[active["Date"] < row["Date"]].sort_values("Date")
            for _, prev_row in prev_rows.iloc[::-1].iterrows():
                if not is_fwd(prev_row):
                    if prev_row["Date"].date() in expanded:
                        expanded.add(d)
                    break

    return expanded


def quarantine_rows(df: pd.DataFrame, dates_to_quarantine: set[datetime.date]) -> tuple[pd.DataFrame, int]:
    """Mark given dates as Is_Stale=1 in the DataFrame. Returns (updated_df, count)."""
    if "Is_Stale" not in df.columns:
        df = df.copy()
        df["Is_Stale"] = 0

    mask = df["Date"].dt.date.isin(dates_to_quarantine) & (df["Is_Stale"] == 0)
    count = int(mask.sum())
    if count > 0:
        df = df.copy()
        df.loc[mask, "Is_Stale"] = 1
    return df, count


def clamp_ohlc(df: pd.DataFrame, ohlc_anomalies: list[Anomaly]) -> tuple[pd.DataFrame, int]:
    """
    Clamp H/L to satisfy OHLC constraints for the given anomaly dates.
    Open and Close are never modified. Skips rows where Open/Close differ by > 40%
    of Close — that spread indicates one of them is itself an OCR error, and clamping
    would produce a wrong Low/High. Returns (updated_df, n_fixed).
    """
    dates_to_fix = {a.date for a in ohlc_anomalies if a.action in ("clamp_hl", "dry_run")}
    if not dates_to_fix:
        return df, 0

    df = df.copy()
    fixed = 0
    mask = df["Date"].dt.date.isin(dates_to_fix) & (df["Is_Stale"] == 0)

    for idx in df[mask].index:
        o = float(df.at[idx, "Open"])
        h = float(df.at[idx, "High"])
        l = float(df.at[idx, "Low"])
        c = float(df.at[idx, "Close"])
        if c <= 0:
            continue
        # Skip if Open and Close are suspiciously far apart — one may be an OCR error
        if abs(o - c) > 0.4 * c:
            continue
        changed = False
        correct_low = min(o, c)
        correct_high = max(o, c)
        if l > correct_low:
            df.at[idx, "Low"] = correct_low
            changed = True
        if h < correct_high:
            df.at[idx, "High"] = correct_high
            changed = True
        if df.at[idx, "Low"] > df.at[idx, "High"]:
            df.at[idx, "Low"] = df.at[idx, "High"]
            changed = True
        if changed:
            fixed += 1

    return df, fixed


def apply_nse_close(df: pd.DataFrame, date: datetime.date, confirmed_close: float) -> pd.DataFrame:
    """Replace OHLCV for a given date with the NSE-confirmed close (flat bar, V=0 if unconfirmed)."""
    df = df.copy()
    mask = (df["Date"].dt.date == date) & (df["Is_Stale"] == 0)
    df.loc[mask, "Close"] = confirmed_close
    df.loc[mask, "Open"] = confirmed_close
    df.loc[mask, "High"] = confirmed_close
    df.loc[mask, "Low"] = confirmed_close
    return df


def push_ticker_to_rtdb(root_ref, csv_path: Path) -> int:
    """Re-push all Is_Stale=0 rows for a ticker from its CSV to RTDB."""
    ticker = csv_path.stem.replace("_cleaned", "")
    short = ticker.split("_")[0].upper()

    df = pd.read_csv(csv_path, parse_dates=["Date"])
    if "Is_Stale" in df.columns:
        df = df[df["Is_Stale"] == 0]
    df = df.sort_values("Date").reset_index(drop=True)

    batch: dict = {}
    total = 0

    for i, row in df.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d")
        close = float(row["Close"]) if pd.notna(row.get("Close")) else None
        prev_close = float(df.iloc[i - 1]["Close"]) if i > 0 and pd.notna(df.iloc[i - 1]["Close"]) else None
        ch = round(close - prev_close, 4) if close is not None and prev_close is not None else None
        pch = round((ch / prev_close) * 100, 4) if ch is not None and prev_close else None

        def _clean(v):
            if v is None:
                return None
            try:
                f = float(v)
                return None if math.isnan(f) or math.isinf(f) else round(f, 4)
            except (TypeError, ValueError):
                return None

        node = {
            "o": _clean(row.get("Open")),
            "h": _clean(row.get("High")),
            "l": _clean(row.get("Low")),
            "c": _clean(close),
            "v": _clean(row.get("Volume")),
            "pc": _clean(prev_close),
            "ch": _clean(ch),
            "pch": _clean(pch),
            "vv": None,
        }
        batch[f"prices/{short}/{date_str}"] = node
        if len(batch) >= 500:
            root_ref.update(batch)
            total += len(batch)
            batch = {}

    if batch:
        root_ref.update(batch)
        total += len(batch)

    return total


def process_ticker(
    csv_path: Path,
    nse_prices: dict[str, float],
    today: datetime.date,
    year_filter: Optional[int],
    dry_run: bool,
    push_rtdb: bool,
    root_ref,
) -> list[Anomaly]:
    ticker = csv_path.stem.replace("_cleaned", "")
    df = pd.read_csv(csv_path, parse_dates=["Date"])

    if "Is_Stale" not in df.columns:
        df["Is_Stale"] = 0

    # Optionally restrict anomaly detection to a single year
    if year_filter:
        scan_mask = df["Date"].dt.year == year_filter
        scan_df = df[scan_mask].copy()
        # Still need full history for spike detection (need prev-day close)
        # So we detect on full df and filter results by year
    scan_df = df

    all_anomalies: list[Anomaly] = []
    all_anomalies.extend(detect_spikes_iterative(scan_df, ticker))
    all_anomalies.extend(detect_ohlc_violations(scan_df, ticker))
    all_anomalies.extend(detect_invalid_prices(scan_df, ticker))

    # Filter by year if requested
    if year_filter:
        all_anomalies = [a for a in all_anomalies if a.date.year == year_filter]

    if not all_anomalies:
        return []

    # Try NSE fix for today's spike/invalid anomalies
    for anomaly in all_anomalies:
        if anomaly.action == "quarantine":
            apply_nse_fix(anomaly, nse_prices, today)

    if dry_run:
        for a in all_anomalies:
            if a.action not in ("nse_fix", "clamp_hl"):
                a.action = "dry_run"
        return all_anomalies

    # Apply changes to CSV
    csv_changed = False

    # Dates that will be quarantined — skip OHLC clamp for them (no point fixing a hidden row)
    spike_dates = {a.date for a in all_anomalies if a.action in ("quarantine", "nse_fix")}

    # 1. Clamp OHLC violations (safe: only modifies H/L, not O/C)
    ohlc_anomalies = [a for a in all_anomalies if a.kind == "ohlc" and a.date not in spike_dates]
    if ohlc_anomalies:
        df, n_clamped = clamp_ohlc(df, ohlc_anomalies)
        if n_clamped > 0:
            log.info("  %s: clamped H/L on %d rows", ticker, n_clamped)
            csv_changed = True
            for a in ohlc_anomalies:
                a.action = "clamp_hl"

    # 2. Apply NSE-confirmed fixes for today's spikes
    nse_fix_anomalies = [a for a in all_anomalies if a.action == "nse_fix"]
    for a in nse_fix_anomalies:
        log.info("  %s %s: NSE fix — %s → %.4f (source: NSE AJAX)",
                 ticker, a.date, a.detail, a.confirmed_close)
        df = apply_nse_close(df, a.date, a.confirmed_close)
        csv_changed = True

    # 3. Quarantine unanswerable spikes/invalid (mark Is_Stale=1 — removed from RTDB)
    quarantine_anomalies = [a for a in all_anomalies if a.action == "quarantine"]
    quarantine_dates: set[datetime.date] = set()
    for a in quarantine_anomalies:
        quarantine_dates.add(a.date)
        log.info("  %s %s: QUARANTINE — %s (no NSE confirmation available)",
                 ticker, a.date, a.detail)

    if quarantine_dates:
        # Also cascade-quarantine forward-fills that inherited a spiked price
        expanded_dates = cascade_quarantine_fwd_fills(df, quarantine_dates)
        cascade_extra = expanded_dates - quarantine_dates
        for d in sorted(cascade_extra):
            log.info("  %s %s: CASCADE QUARANTINE — forward-fill from spiked date", ticker, d)

        df, n_quarantined = quarantine_rows(df, expanded_dates)
        if n_quarantined > 0:
            log.info("  %s: marked %d rows Is_Stale=1 (%d direct + %d cascade)",
                     ticker, n_quarantined, len(quarantine_dates), len(cascade_extra))
            csv_changed = True

    if csv_changed:
        df.to_csv(csv_path, index=False)
        log.info("  %s: CSV updated", ticker)

        if push_rtdb and root_ref is not None:
            pushed = push_ticker_to_rtdb(root_ref, csv_path)
            log.info("  %s: RTDB re-pushed %d nodes", ticker, pushed)

    return all_anomalies


def print_report(anomalies: list[Anomaly]) -> None:
    if not anomalies:
        log.info("No anomalies detected.")
        return

    by_ticker: dict[str, list[Anomaly]] = {}
    for a in anomalies:
        by_ticker.setdefault(a.ticker, []).append(a)

    log.info("=" * 70)
    log.info("ANOMALY REPORT — %d total across %d tickers", len(anomalies), len(by_ticker))
    log.info("=" * 70)
    for ticker in sorted(by_ticker):
        rows = by_ticker[ticker]
        for a in sorted(rows, key=lambda x: x.date):
            nse_note = f" → NSE={a.confirmed_close:.4f}" if a.confirmed_close else ""
            log.info(
                "  [%s] %s %s | %s | %s%s",
                a.action.upper(), ticker, a.date, a.kind.upper(), a.detail, nse_note,
            )
    log.info("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect anomalies but do not modify CSVs or RTDB")
    parser.add_argument("--ticker", help="Process single ticker only")
    parser.add_argument("--year", type=int, default=None,
                        help="Restrict anomaly scan to this year (e.g. 2026)")
    parser.add_argument("--push-rtdb", action="store_true",
                        help="Re-push affected tickers to RTDB after CSV changes")
    args = parser.parse_args()

    csv_files = sorted(DATA_CLEANED.glob("*_cleaned.csv"))
    if args.ticker:
        csv_files = [f for f in csv_files if args.ticker.upper() in f.stem.upper()]
    if not csv_files:
        log.error("No CSVs found in %s", DATA_CLEANED)
        sys.exit(1)

    today = datetime.date.today()
    nse_prices = fetch_nse_live_prices()

    root_ref = None
    if not args.dry_run and args.push_rtdb:
        sys.path.insert(0, str(REPO_ROOT))
        from pipeline.scripts.firebase_client import get_rtdb
        root_ref = get_rtdb()

    all_anomalies: list[Anomaly] = []

    for csv_path in csv_files:
        try:
            found = process_ticker(
                csv_path, nse_prices, today,
                args.year, args.dry_run, args.push_rtdb, root_ref,
            )
            all_anomalies.extend(found)
        except Exception as exc:
            log.error("  %s: FAILED — %s", csv_path.stem, exc, exc_info=True)

    print_report(all_anomalies)
    log.info(
        "Done — %d anomalies found (%d quarantined, %d nse_fixed, %d hl_clamped, %d dry_run)",
        len(all_anomalies),
        sum(1 for a in all_anomalies if a.action == "quarantine"),
        sum(1 for a in all_anomalies if a.action == "nse_fix"),
        sum(1 for a in all_anomalies if a.action == "clamp_hl"),
        sum(1 for a in all_anomalies if a.action == "dry_run"),
    )


if __name__ == "__main__":
    main()
