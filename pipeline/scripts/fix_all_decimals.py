"""
Comprehensive decimal-error fix for ALL companies in both local CSVs and RTDB.

Rule (from user): "any sudden rise and drop which is so high than expected →
missing decimal, divide by 100".

Detection:
  A price at day t is a spike when:
    - price[t] / price[t-1] > JUMP_RATIO  (jumped up from previous day)
      AND price[t] / price[t+1] > JUMP_RATIO  (dropped right back)
    - OR (boundary): first/last day and ratio to only neighbor > JUMP_RATIO
  Fixed value = price[t] / 100, accepted only if it is within RESTORE_RANGE
  of the surrounding prices.

This correctly skips companies like OCH that traded at 110 KES for months
(sustained period → not a spike), and catches single-/few-day OCR glitches.

Applies to Open, High, Low, Close columns independently.

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \\
    python pipeline/scripts/fix_all_decimals.py [--dry-run] [--ticker SCOM]
"""
import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_CLEANED = REPO_ROOT / "data" / "cleaned"
PRICE_COLS = ["Open", "High", "Low", "Close"]

# A single-day ratio ≥ 10x up AND ≥ 10x down = spike
JUMP_RATIO = 10.0
# After dividing by 10 or 100, the result must stay within 2x of neighbors.
# Tight enough to reject ambiguous OCR corruption (OCH 110→11 when ref=5.3 has ratio=2.07 > 2.0).
RESTORE_LO = 0.5
RESTORE_HI = 2.0


def _best_candidate(val: float, ref: float, direction: str) -> float | None:
    """
    Return the corrected value for an outlier.

    direction="high": val is too large — try dividing by 10 or 100.
    direction="low":  val is too small — try multiplying by 10 or 100.

    Accepts the first candidate within [RESTORE_LO * ref, RESTORE_HI * ref].
    Returns None if no candidate passes.
    """
    if direction == "high":
        for divisor in (10, 100):
            cand = round(val / divisor, 4)
            if RESTORE_LO * ref <= cand <= RESTORE_HI * ref:
                return cand
    else:  # "low"
        for multiplier in (10, 100):
            cand = round(val * multiplier, 4)
            if RESTORE_LO * ref <= cand <= RESTORE_HI * ref:
                return cand
    return None


def _fix_spikes_in_series(values: list[float | None]) -> tuple[list[float | None], int]:
    """
    Detect and fix both upward and downward decimal spikes:
      - Upward:   val ≥ JUMP_RATIO × neighbor  → OCR added digit(s) → divide by 10 or 100
      - Downward: val ≤ neighbor / JUMP_RATIO  → OCR dropped digit(s) → multiply by 10 or 100

    Picks the factor that brings the value to within [RESTORE_LO, RESTORE_HI] of neighbors.
    Returns (fixed_values, n_changes).
    """
    n = len(values)
    out = list(values)
    changes = 0

    for i, val in enumerate(values):
        if val is None or val <= 0:
            continue

        prev = next((values[j] for j in range(i - 1, -1, -1) if values[j] and values[j] > 0), None)
        nxt  = next((values[j] for j in range(i + 1, n)       if values[j] and values[j] > 0), None)

        direction = None
        ref = None

        if prev and nxt:
            if (val / prev >= JUMP_RATIO) and (val / nxt >= JUMP_RATIO):
                direction = "high"
                ref = (prev + nxt) / 2
            elif (prev / val >= JUMP_RATIO) and (nxt / val >= JUMP_RATIO):
                direction = "low"
                ref = (prev + nxt) / 2
        elif prev and not nxt:
            if val / prev >= JUMP_RATIO:
                direction = "high"
                ref = prev
            elif prev / val >= JUMP_RATIO:
                direction = "low"
                ref = prev
        elif nxt and not prev:
            if val / nxt >= JUMP_RATIO:
                direction = "high"
                ref = nxt
            elif nxt / val >= JUMP_RATIO:
                direction = "low"
                ref = nxt

        if direction and ref and ref > 0:
            candidate = _best_candidate(val, ref, direction)
            if candidate is not None:
                out[i] = candidate
                changes += 1

    return out, changes


def fix_csv_decimals(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Apply spike-detection fix to a cleaned-CSV DataFrame."""
    df = df.copy().sort_values("Date").reset_index(drop=True)
    total_changes = 0

    for col in PRICE_COLS:
        if col not in df.columns:
            continue
        series = df[col].tolist()
        fixed, n = _fix_spikes_in_series(series)
        if n:
            df[col] = fixed
            total_changes += n

    return df, total_changes


def build_rtdb_records(df: pd.DataFrame) -> dict:
    """Convert fixed CSV DataFrame to RTDB-ready {date_str: fields} dict."""
    df = df.copy()
    if "Is_Stale" in df.columns:
        df = df[df["Is_Stale"] == 0]
    df = df.sort_values("Date").reset_index(drop=True)

    records: dict = {}
    for i, row in df.iterrows():
        date_str = row["Date"].strftime("%Y-%m-%d")
        close = float(row["Close"]) if pd.notna(row.get("Close")) else None
        prev_close = float(df.iloc[i - 1]["Close"]) if i > 0 and pd.notna(df.iloc[i - 1]["Close"]) else None
        ch = round(close - prev_close, 4) if close is not None and prev_close is not None else None
        pch = round((ch / prev_close) * 100, 4) if ch is not None and prev_close else None
        records[date_str] = {
            "o":   float(row["Open"])   if pd.notna(row.get("Open"))   else None,
            "h":   float(row["High"])   if pd.notna(row.get("High"))   else None,
            "l":   float(row["Low"])    if pd.notna(row.get("Low"))    else None,
            "c":   close,
            "v":   float(row["Volume"]) if pd.notna(row.get("Volume")) else None,
            "pc":  prev_close,
            "ch":  ch,
            "pch": pch,
            "vv":  None,
        }
    return records


def push_to_rtdb(root_ref, ticker: str, records: dict) -> int:
    """Overwrite all price nodes for this ticker in RTDB."""
    import math
    short = ticker.split("_")[0].upper()
    batch: dict = {}
    total = 0
    for date_str, fields in records.items():
        node = {}
        for k, v in fields.items():
            if v is None:
                node[k] = None
            else:
                try:
                    f = float(v)
                    node[k] = None if math.isnan(f) or math.isinf(f) else round(f, 4)
                except (TypeError, ValueError):
                    node[k] = None
        batch[f"prices/{short}/{date_str}"] = node
        if len(batch) >= 500:
            root_ref.update(batch)
            total += len(batch)
            batch = {}
    if batch:
        root_ref.update(batch)
        total += len(batch)
    return total


def process_ticker(csv_path: Path, root_ref, dry_run: bool) -> tuple[int, int]:
    """Returns (cells_fixed, rtdb_nodes_written)."""
    ticker = csv_path.stem.replace("_cleaned", "")
    df = pd.read_csv(csv_path, parse_dates=["Date"])
    if df.empty:
        log.warning("  %s: empty CSV, skipping", ticker)
        return 0, 0

    fixed_df, n_fixed = fix_csv_decimals(df)

    if n_fixed > 0:
        log.info("  %s: fixed %d decimal cell(s)", ticker, n_fixed)
        if dry_run:
            for col in PRICE_COLS:
                if col not in df.columns:
                    continue
                orig_col = df[col].tolist()
                fix_col  = fixed_df[col].tolist()
                shown = 0
                for idx, (o, f) in enumerate(zip(orig_col, fix_col)):
                    if o != f:
                        d = df.at[idx, "Date"]
                        d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
                        log.info("    %s %s: %.4f → %.4f", d_str, col, o, f)
                        shown += 1
                        if shown >= 10:
                            remaining = sum(1 for a, b in zip(orig_col, fix_col) if a != b) - shown
                            if remaining > 0:
                                log.info("    ... and %d more %s changes", remaining, col)
                            break
    else:
        log.debug("  %s: no decimal errors found", ticker)

    if dry_run:
        return n_fixed, 0

    if n_fixed > 0:
        fixed_df.to_csv(csv_path, index=False)
        log.info("  %s: saved fixed CSV", ticker)

    records = build_rtdb_records(fixed_df)
    if root_ref is not None:
        written = push_to_rtdb(root_ref, ticker, records)
        log.info("  %s: wrote %d RTDB nodes", ticker, written)
    else:
        written = 0

    return n_fixed, written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    parser.add_argument("--ticker", help="Process single ticker only (e.g. SCOM)")
    parser.add_argument("--csv-only", action="store_true", help="Fix CSVs but skip RTDB push")
    args = parser.parse_args()

    root_ref = None
    if not args.dry_run and not args.csv_only:
        sys.path.insert(0, str(REPO_ROOT))
        from pipeline.scripts.firebase_client import get_rtdb
        root_ref = get_rtdb()

    csv_files = sorted(DATA_CLEANED.glob("*_cleaned.csv"))
    if args.ticker:
        csv_files = [f for f in csv_files if args.ticker.upper() in f.stem.upper()]
    if not csv_files:
        log.error("No CSVs found in %s", DATA_CLEANED)
        sys.exit(1)

    log.info("Processing %d tickers (dry_run=%s, csv_only=%s)", len(csv_files), args.dry_run, args.csv_only)

    total_cells = 0
    total_nodes = 0
    tickers_fixed: list[str] = []

    for csv_path in csv_files:
        try:
            cells, nodes = process_ticker(csv_path, root_ref, args.dry_run)
            total_cells += cells
            total_nodes += nodes
            if cells > 0:
                tickers_fixed.append(csv_path.stem.replace("_cleaned", ""))
        except Exception as exc:
            log.error("  %s: FAILED — %s", csv_path.stem, exc, exc_info=True)

    log.info("=" * 60)
    log.info("Done — %d decimal cells fixed across %d tickers", total_cells, len(tickers_fixed))
    if tickers_fixed:
        log.info("Affected tickers: %s", ", ".join(tickers_fixed))
    if not args.dry_run:
        log.info("RTDB nodes written: %d", total_nodes)


if __name__ == "__main__":
    main()
