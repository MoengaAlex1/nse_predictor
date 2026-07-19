"""
weekend_refinement.py

Runs Saturday and Sunday after NSE markets have closed for the week.

For every company:
  1. Fetches the latest Firestore snapshot (which has next_trading_day +
     predicted_price_KES written by Friday's inference run).
  2. Reads the actual closing price for that target date from the cleaned CSV.
  3. Computes: absolute error, percentage error, and whether the direction
     (up/down) was predicted correctly.
  4. Writes a refinement doc to companies/{ticker}/refinements/{date}.
  5. Updates the company's public doc with recent accuracy metrics so the
     frontend can display model performance.

The Sunday full retrain (run_training.py) uses all available data — this
script feeds it context on which companies need the most attention.

Run: python pipeline/scripts/weekend_refinement.py
Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import sys
import logging
from pathlib import Path
from datetime import date, timedelta

import numpy as np
import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies, DATA_CLEANED
from scripts.push_to_firestore import get_db, update_company_public

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY = date.today().isoformat()
LOOKBACK_DAYS = 5   # compare predictions for the most recent N trading days


def _last_n_trading_days(n: int, up_to: date | None = None) -> list[date]:
    """Return the n most recent trading days on or before up_to (default: today)."""
    days: list[date] = []
    d = up_to or date.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days


def _load_csv_prices(csv_path: Path) -> dict[str, float]:
    """Return {date_iso: close_price} for all rows in the cleaned CSV."""
    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            return {}
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=True, format="mixed")
        df = df.dropna(subset=["Close"])
        return {d.date().isoformat(): round(float(p), 4)
                for d, p in zip(df[date_col], df["Close"])}
    except Exception as e:
        log.warning("CSV load failed for %s: %s", csv_path.name, e)
        return {}


def _fetch_snapshots(db, ticker_safe: str) -> list[dict]:
    """Fetch recent snapshots from Firestore for this ticker."""
    try:
        from google.cloud.firestore import Query
        ref = (db.collection("companies")
                 .document(ticker_safe)
                 .collection("snapshots")
                 .order_by("__name__", direction=Query.DESCENDING)
                 .limit(LOOKBACK_DAYS))
        return [{"id": d.id, **d.to_dict()} for d in ref.stream()]
    except Exception as e:
        log.warning("Snapshot fetch failed for %s: %s", ticker_safe, e)
        return []


def _write_refinement(db, ticker_safe: str, ref_date: str, data: dict) -> None:
    (db.collection("companies")
       .document(ticker_safe)
       .collection("refinements")
       .document(ref_date)
       .set(data))


def analyse_company(db, company: dict, csv_prices: dict[str, float]) -> dict | None:
    """Compare recent predictions vs actuals. Returns summary or None on failure."""
    safe = company["ticker"].replace(".", "_")
    snapshots = _fetch_snapshots(db, safe)
    if not snapshots:
        return None

    errors: list[dict] = []
    for snap in snapshots:
        target = snap.get("next_trading_day")
        predicted = snap.get("predicted_price_KES")
        actual = csv_prices.get(target) if target else None

        if target is None or predicted is None or actual is None:
            continue

        abs_err = abs(actual - predicted)
        pct_err = abs_err / actual * 100 if actual else None
        current_price = snap.get("current_price_KES", actual)
        direction_predicted = predicted > current_price
        direction_actual = actual > current_price
        direction_correct = direction_predicted == direction_actual

        entry = {
            "date":              TODAY,
            "target_date":       target,
            "predicted_price":   round(predicted, 4),
            "actual_price":      round(actual, 4),
            "abs_error":         round(abs_err, 4),
            "pct_error":         round(pct_err, 2) if pct_err is not None else None,
            "direction_correct": direction_correct,
            "signal_predicted":  snap.get("signal"),
        }
        errors.append(entry)
        _write_refinement(db, safe, target, entry)
        log.info(
            "%-20s  target=%-12s  pred=%-10.4f  actual=%-10.4f  err=%+.2f%%  dir=%s",
            safe, target, predicted, actual,
            pct_err if pct_err is not None else float("nan"),
            "✓" if direction_correct else "✗",
        )

    if not errors:
        return None

    mape = float(np.mean([e["pct_error"] for e in errors if e["pct_error"] is not None]))
    dir_acc = float(np.mean([e["direction_correct"] for e in errors])) * 100

    summary = {
        "recent_mape":              round(mape, 2),
        "recent_direction_acc":     round(dir_acc, 1),
        "refinement_date":          TODAY,
        "refinement_sample_size":   len(errors),
    }
    update_company_public(db, safe, summary)
    return summary


def main() -> None:
    db = get_db()
    companies = load_companies()
    company_map = {c["ticker"].replace(".", "_"): c for c in companies}

    # Build a unified price lookup from all cleaned CSVs
    all_prices: dict[str, dict[str, float]] = {}
    for csv_path in DATA_CLEANED.glob("*_cleaned.csv"):
        safe = csv_path.stem.replace("_cleaned", "")
        all_prices[safe] = _load_csv_prices(csv_path)

    results: list[tuple[str, float, float]] = []   # (ticker, mape, dir_acc)
    for safe, company in company_map.items():
        prices = all_prices.get(safe, {})
        summary = analyse_company(db, company, prices)
        if summary:
            results.append((safe, summary["recent_mape"], summary["recent_direction_acc"]))

    # Log worst performers so Sunday retrain can prioritise them
    results.sort(key=lambda x: x[1], reverse=True)
    log.info("\n=== Weekend Refinement Summary ===")
    log.info("Analysed %d companies", len(results))
    log.info("\nTop 10 worst MAPE (need most improvement):")
    for ticker, mape, dir_acc in results[:10]:
        log.info("  %-20s  MAPE=%.1f%%  DirectionAcc=%.0f%%", ticker, mape, dir_acc)

    if results:
        avg_mape = float(np.mean([r[1] for r in results]))
        avg_dir = float(np.mean([r[2] for r in results]))
        log.info("\nPortfolio average  MAPE=%.1f%%  DirectionAcc=%.0f%%", avg_mape, avg_dir)


if __name__ == "__main__":
    main()
