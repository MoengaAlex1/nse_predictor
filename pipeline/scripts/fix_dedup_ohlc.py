"""
One-time cleanup: fix duplicates and OHLC violations across all cleaned CSVs.

Root cause: fill_missing_dates.py added Is_Stale=0 forward-fill rows (Volume=0,
OHLC flat) for dates that already had Is_Stale=1 actual-trade rows. This means
the RTDB received wrong forward-fill prices instead of real trading data.

Fix strategy for duplicate dates:
- Priority: (Is_Stale=0, V>0) > (Is_Stale=1, V>0) > (any, V=0)
- When Is_Stale=0 is a forward-fill (V=0, OHLC flat) and Is_Stale=1 has real
  volume, promote the Is_Stale=1 row → Is_Stale=0 and remove the forward-fill.

Additional fixes:
- SLAM July 21-24: OCR misassignment at 291.50 KES (33x jump). Forward-fill from 8.60.
- OHLC constraint violations: clamp impossible Low (> min(O,C)) and High (< max(O,C)).

Usage:
  FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \\
    python pipeline/scripts/fix_dedup_ohlc.py [--dry-run] [--ticker SCOM] [--csv-only]
"""
import argparse
import datetime
import logging
import math
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_CLEANED = REPO_ROOT / "data" / "cleaned"


def _is_forward_fill_row(row) -> bool:
    """True when a row looks like a forward-fill placeholder (V=0, OHLC all equal)."""
    try:
        o, h, l, c, v = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]), float(row["Volume"])
        return v == 0 and o == h == l == c
    except (TypeError, ValueError, KeyError):
        return False


def dedup_and_promote(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    For each date that has duplicates:
    1. If Is_Stale=0 row is a forward-fill (V=0, OHLC flat) AND Is_Stale=1 row
       has actual volume: promote the Is_Stale=1 row, drop the forward-fill.
    2. If multiple Is_Stale=0 rows with volume: keep max-volume one.
    Returns (fixed_df, n_changed).
    """
    if "Is_Stale" not in df.columns:
        return df, 0

    changed = 0
    result_rows = []

    for date_val, group in df.groupby("Date", sort=False):
        if len(group) == 1:
            result_rows.append(group)
            continue

        active_g = group[group["Is_Stale"] == 0]
        stale_g = group[group["Is_Stale"] == 1]

        # Case 1: Is_Stale=0 forward-fill + Is_Stale=1 real data
        ff_mask = active_g.apply(_is_forward_fill_row, axis=1)
        fwd_fills = active_g[ff_mask]
        real_active = active_g[~ff_mask]

        # Find Is_Stale=1 rows with actual volume (real trades)
        real_stale = stale_g[stale_g["Volume"] > 0]

        if not fwd_fills.empty and real_active.empty and not real_stale.empty:
            # Promote best stale (highest volume) to active; drop forward-fill(s)
            best_stale = real_stale.sort_values("Volume", ascending=False).iloc[0:1].copy()
            best_stale["Is_Stale"] = 0
            other_stale = stale_g[~stale_g.index.isin(best_stale.index)]
            result_rows.append(best_stale)
            result_rows.append(other_stale)
            changed += len(fwd_fills)
            continue

        # Case 2: Multiple Is_Stale=0 rows — keep highest volume
        if len(active_g) > 1:
            best_active = active_g.sort_values("Volume", ascending=False).iloc[0:1]
            rest_active = active_g[~active_g.index.isin(best_active.index)].copy()
            rest_active["Is_Stale"] = 1  # demote extras to stale
            changed += len(rest_active)
            result_rows.append(best_active)
            result_rows.append(rest_active)
            result_rows.append(stale_g)
            continue

        # No change needed
        result_rows.append(group)

    if not result_rows:
        return df, 0

    fixed = pd.concat(result_rows, ignore_index=True).sort_values("Date")
    return fixed, changed


def fix_ohlc(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Fix impossible OHLC values for Is_Stale=0 rows only.
    - Low > min(Open, Close) → set Low = min(Open, Close)
    - High < max(Open, Close) → set High = max(Open, Close)
    """
    active_mask = df["Is_Stale"] == 0 if "Is_Stale" in df.columns else pd.Series(True, index=df.index)
    df = df.copy()
    fixed = 0

    for idx in df[active_mask].index:
        o = df.at[idx, "Open"]
        h = df.at[idx, "High"]
        l = df.at[idx, "Low"]
        c = df.at[idx, "Close"]
        if any(pd.isna(x) for x in [o, h, l, c]):
            continue

        correct_low = min(o, c)
        correct_high = max(o, c)
        changed = False

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


def fix_slam_spike(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    SLAM-specific: replace July 21-24 2026 OCR misassignment (291.50 KES).
    Forward-fill from the last confirmed good close before the spike.
    """
    spike_dates = pd.to_datetime(["2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24"])
    spike_mask = df["Date"].isin(spike_dates)
    if "Is_Stale" in df.columns:
        spike_mask = spike_mask & (df["Is_Stale"] == 0)

    spiked = df[spike_mask & (df["Close"] > 50)]
    if spiked.empty:
        return df, 0

    good = df[df["Is_Stale"] == 0] if "Is_Stale" in df.columns else df
    good = good[good["Date"] < pd.Timestamp("2026-07-21")].sort_values("Date")
    if good.empty:
        return df, 0

    last_close = good.iloc[-1]["Close"]
    log.info("  SLAM: replacing %d spike rows (Close=%.2f) with forward-fill %.2f",
             len(spiked), spiked.iloc[0]["Close"], last_close)

    df = df.copy()
    for idx in spiked.index:
        df.at[idx, "Open"] = last_close
        df.at[idx, "High"] = last_close
        df.at[idx, "Low"] = last_close
        df.at[idx, "Close"] = last_close
        df.at[idx, "Volume"] = 0

    return df, len(spiked)


def push_to_rtdb(root_ref, ticker: str, df: pd.DataFrame) -> int:
    short = ticker.split("_")[0].upper()
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

        def clean(v):
            if v is None:
                return None
            try:
                f = float(v)
                return None if math.isnan(f) or math.isinf(f) else round(f, 4)
            except (TypeError, ValueError):
                return None

        node = {
            "o": clean(row.get("Open")),
            "h": clean(row.get("High")),
            "l": clean(row.get("Low")),
            "c": clean(close),
            "v": clean(row.get("Volume")),
            "pc": clean(prev_close),
            "ch": clean(ch),
            "pch": clean(pch),
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


def process_ticker(csv_path: Path, root_ref, dry_run: bool, csv_only: bool, force_push: bool = False) -> dict:
    ticker = csv_path.stem.replace("_cleaned", "")
    df = pd.read_csv(csv_path, parse_dates=["Date"])

    stats: dict = {"ticker": ticker, "promoted": 0, "ohlc_fixed": 0, "slam_fixed": 0, "rtdb_pushed": 0}

    df, n_promoted = dedup_and_promote(df)
    stats["promoted"] = n_promoted

    df, n_ohlc = fix_ohlc(df)
    stats["ohlc_fixed"] = n_ohlc

    if "SLAM" in ticker.upper():
        df, n_slam = fix_slam_spike(df)
        stats["slam_fixed"] = n_slam

    changed = n_promoted + n_ohlc + stats["slam_fixed"]
    if changed == 0 and not force_push:
        return stats

    if not dry_run:
        if changed > 0:
            df.to_csv(csv_path, index=False)
        if not csv_only and root_ref is not None:
            pushed = push_to_rtdb(root_ref, ticker, df)
            stats["rtdb_pushed"] = pushed
            log.info("  %s: promoted=%d ohlc=%d slam=%d → rtdb=%d",
                     ticker, n_promoted, n_ohlc, stats["slam_fixed"], pushed)
        else:
            log.info("  %s: promoted=%d ohlc=%d slam=%d (csv-only)",
                     ticker, n_promoted, n_ohlc, stats["slam_fixed"])
    else:
        log.info("  %s [DRY]: promoted=%d ohlc=%d slam=%d",
                 ticker, n_promoted, n_ohlc, stats["slam_fixed"])

    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ticker", help="Process single ticker only")
    parser.add_argument("--csv-only", action="store_true")
    parser.add_argument("--force-push", action="store_true",
                        help="Push all tickers to RTDB even if no changes detected")
    args = parser.parse_args()

    csv_files = sorted(DATA_CLEANED.glob("*_cleaned.csv"))
    if args.ticker:
        csv_files = [f for f in csv_files if args.ticker.upper() in f.stem.upper()]
    if not csv_files:
        log.error("No CSVs found in %s", DATA_CLEANED)
        sys.exit(1)

    root_ref = None
    if not args.dry_run and not args.csv_only:
        sys.path.insert(0, str(REPO_ROOT))
        from pipeline.scripts.firebase_client import get_rtdb
        root_ref = get_rtdb()

    totals = {"promoted": 0, "ohlc_fixed": 0, "slam_fixed": 0, "rtdb_pushed": 0}
    for csv_path in csv_files:
        try:
            stats = process_ticker(csv_path, root_ref, args.dry_run, args.csv_only, args.force_push)
            for k in totals:
                totals[k] += stats.get(k, 0)
        except Exception as exc:
            log.error("  %s: FAILED — %s", csv_path.stem, exc, exc_info=True)

    log.info("=" * 60)
    log.info("Done — promoted=%d ohlc_fixed=%d slam_fixed=%d rtdb_pushed=%d",
             totals["promoted"], totals["ohlc_fixed"], totals["slam_fixed"], totals["rtdb_pushed"])


if __name__ == "__main__":
    main()
