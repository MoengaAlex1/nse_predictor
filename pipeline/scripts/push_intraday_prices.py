"""
push_intraday_prices.py

Lightweight intraday price push to Firestore.
Runs immediately AFTER scrape_nse_prices.py in the same GitHub Actions job,
so the updated CSVs are already in /tmp/nse_csvs/ from the scrape step.

Designed to run 3× per trading day (EAT):
  09:00 — opening snapshot
  14:00 — midday update (overwrites today's entry)
  15:30 — closing price (final, after NSE closes at 15:00 EAT)

For each company:
  1. Read the freshly-scraped CSV from /tmp (or download from Storage if missing).
  2. Build price_history (all non-stale, Mon-Fri rows up to today).
  3. Compute current_price and change_pct_today.
  4. Push to Firestore via update_company_public (merge=True).
     Only updates: current_price, change_pct_today, price_history,
                   price_preview, last_updated.
     Leaves untouched: signal, snapshot, technicals.
  5. Merge today's Volume into companies/{doc_id}/technicals/{TODAY}
     via merge=True so backfill_most_active.py picks up intraday volume
     changes on its next run (Most Active list truly varies through the
     day, not just between inference runs). Inference-computed fields
     on the same doc (RSI, MACD, SMA, avg_volume_30d) survive merge.

The nightly daily_update.yml handles full model retraining and signal refresh.
"""

import sys
import os
import logging
from pathlib import Path
from datetime import date, datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from scripts.push_to_firestore import (
    get_db,
    update_company_public,
    download_model_from_storage,
)
from scripts.scrape_nse_prices import CSVS_TMP, _load_local_csv, _clean_df
from config import load_companies

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_EAT = timezone(timedelta(hours=3))
_NOW_EAT = datetime.now(_EAT)
TODAY_EAT = _NOW_EAT.strftime("%Y-%m-%d")
TIME_EAT = _NOW_EAT.strftime("%H:%M")

TODAY = date.today().isoformat()
_TODAY_TS = pd.Timestamp(TODAY)


def _get_csv(safe: str) -> pd.DataFrame | None:
    """
    Return a clean DataFrame for `safe` ticker.
    Prefers the /tmp CSV already written by the scrape step;
    falls back to downloading from Firebase Storage.
    """
    local_path = CSVS_TMP / f"{safe}_cleaned.csv"

    if not local_path.exists():
        CSVS_TMP.mkdir(parents=True, exist_ok=True)
        ok = download_model_from_storage(
            f"data/cleaned/{safe}_cleaned.csv", str(local_path)
        )
        if not ok:
            log.warning("%s: CSV not found in /tmp or Storage — skipping", safe)
            return None

    df = _load_local_csv(local_path)
    if df is None or df.empty:
        log.warning("%s: CSV is empty — skipping", safe)
        return None

    df = _clean_df(df)

    # Drop stale/future/weekend rows
    if "Is_Stale" in df.columns:
        df = df[df["Is_Stale"] != 1]
    df = df[df.index <= _TODAY_TS]
    df = df[df.index.dayofweek < 5]

    return df if not df.empty else None


def _build_intraday_today(db, doc_id: str, current_price: float) -> list[dict]:
    """
    Read existing intraday state from Firestore, archive previous day if needed,
    and return the updated intraday_today list with current_price appended/replaced.
    """
    doc_ref = db.collection("companies").document(doc_id)
    doc_snap = doc_ref.get()
    existing = doc_snap.to_dict() if doc_snap.exists else {}

    stored_date: str | None = existing.get("intraday_date")
    stored_points: list = existing.get("intraday_today") or []

    # Archive previous day's data to subcollection when the date rolls over
    if stored_date and stored_date != TODAY_EAT and stored_points:
        n_archived = len(stored_points)
        (doc_ref.collection("intraday")
                .document(stored_date)
                .set({"date": stored_date, "points": stored_points}))
        log.info("%s: archived intraday %s (%d pts)", doc_id, stored_date, n_archived)
        stored_points = []

    # Append or replace the current time's snapshot (idempotent on same-minute reruns)
    updated = [p for p in stored_points if p.get("time") != TIME_EAT]
    updated.append({"time": TIME_EAT, "price": current_price})
    updated.sort(key=lambda p: p["time"])
    return updated


def _push_intraday_volume(db, doc_id: str, df: pd.DataFrame) -> int | None:
    """If today's row has a Volume value in the scraped CSV, merge it into
    companies/{doc_id}/technicals/{TODAY_EAT} so Most Active can be
    computed from live intraday transactions. Inference-computed fields
    (RSI, MACD, SMA, avg_volume_30d) on the same doc survive merge=True.
    Returns the volume written, or None when not available."""
    if "Volume" not in df.columns:
        return None
    today_ts = pd.Timestamp(TODAY_EAT)
    today_rows = df[df.index == today_ts]
    if today_rows.empty:
        return None
    val = today_rows["Volume"].iloc[-1]
    if pd.isna(val) or val <= 0:
        return None
    volume = int(val)
    (db.collection("companies").document(doc_id)
        .collection("technicals").document(TODAY_EAT)
        .set(
            {
                "date":         TODAY_EAT,
                "volume":       volume,
                "last_updated": _NOW_EAT.isoformat(),
            },
            merge=True,
        )
    )
    return volume


def push_company(company: dict, db) -> dict:
    """Read the scraped CSV and push a price-only update to Firestore."""
    safe = company["ticker"].replace(".", "_")   # used for CSV file lookup only
    doc_id = company["short"]                    # Firestore document key (e.g. "BRIT")

    df = _get_csv(safe)
    if df is None:
        return {"ticker": doc_id, "pushed": False}

    # Build price_history array
    price_history = [
        {"date": idx.strftime("%Y-%m-%d"), "price": round(float(val), 4)}
        for idx, val in df["Close"].items()
        if not pd.isna(val)
    ]
    if not price_history:
        return {"ticker": doc_id, "pushed": False}

    current_price = round(float(df["Close"].iloc[-1]), 4)

    # change_pct_today: last two distinct close prices
    closes = df["Close"].dropna()
    if len(closes) >= 2:
        prev = float(closes.iloc[-2])
        change_pct = float((current_price - prev) / prev * 100) if prev > 0 else 0.0
        # Cap at NSE circuit-breaker +/- 15%
        change_pct = max(-15.0, min(15.0, change_pct))
    else:
        change_pct = 0.0

    # Build intraday_today: accumulate snapshots throughout the trading day
    intraday_today = _build_intraday_today(db, doc_id, current_price)

    update_company_public(db, doc_id, {
        "current_price":    current_price,
        "change_pct_today": round(change_pct, 4),
        "price_history":    price_history,
        "price_preview":    [p["price"] for p in price_history[-30:]],
        "last_updated":     TODAY,
        "intraday_today":   intraday_today,
        "intraday_date":    TODAY_EAT,
    })

    # Also write today's volume to the technicals subcollection so
    # Most Active updates within the day. merge=True preserves the
    # RSI/MACD/etc that inference writes at 18:30 EAT.
    volume = _push_intraday_volume(db, doc_id, df)

    log.info(
        "%-20s  price=%.4f  chg=%+.2f%%  pts=%d  intraday=%d  vol=%s",
        doc_id, current_price, change_pct, len(price_history), len(intraday_today),
        f"{volume:,}" if volume else "—",
    )
    return {"ticker": doc_id, "pushed": True, "price": current_price, "volume": volume}


def main() -> None:
    # NSE is closed on weekends — writing intraday snapshots on a non-trading day
    # would pollute the 1D chart with stale/rumour prices.
    if date.today().weekday() >= 5:
        log.info("NSE closed today (%s). Skipping intraday push.", date.today().strftime("%A %Y-%m-%d"))
        return

    CSVS_TMP.mkdir(parents=True, exist_ok=True)
    db = get_db()
    companies = load_companies()

    ticker_filter = os.environ.get("NSE_TICKERS_FILTER", "").strip()
    if ticker_filter:
        allowed = {t.strip().upper() for t in ticker_filter.split(",") if t.strip()}
        companies = [c for c in companies if c["ticker"].upper() in allowed]
        log.info("NSE_TICKERS_FILTER: pushing %d companies", len(companies))

    log.info("=== Intraday price push | %s | %d companies ===", TODAY, len(companies))

    pushed = 0
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(push_company, c, db): c for c in companies}
        for fut in as_completed(futures):
            co = futures[fut]
            try:
                res = fut.result()
                if res["pushed"]:
                    pushed += 1
            except Exception as exc:
                log.error("Error pushing %s: %s", co["ticker"], exc, exc_info=True)

    log.info("Push complete: %d/%d companies updated in Firestore.", pushed, len(companies))


if __name__ == "__main__":
    main()
