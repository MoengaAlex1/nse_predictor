"""
apply_pdf_backfill.py  –  One-time backfill for July 21 and 22, 2026.

Prices extracted visually from:
  https://www.nse.co.ke/wp-content/uploads/21-JUL-26.pdf
  https://www.nse.co.ke/wp-content/uploads/22-JUL-26.pdf

Column layout (confirmed via PREV PRICE cross-check):
  52WK HIGH | 52WK LOW | Security Name | ISIN | STATUS | HIGH | LOW | VWAP | PREV PRICE | VOLUME

July 18 PDF returned HTTP 404 — no data available for that date.

Usage:
    python apply_pdf_backfill.py [--dry-run]

Env: FIREBASE_SERVICE_ACCOUNT_JSON, FIREBASE_STORAGE_BUCKET
"""
import argparse
import logging
import sys
import tempfile
from pathlib import Path

import pandas as pd

PIPELINE_ROOT = Path(__file__).parent / "pipeline"
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from pipeline.scripts.push_to_firestore import (
    get_db,
    download_model_from_storage,
    upload_model_to_storage,
)
from pipeline.config import load_companies

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CSVS_TMP = Path(tempfile.gettempdir()) / "nse_pdf_backfill"

# ─── Extracted prices ─────────────────────────────────────────────────────────
# Format: "TICKER": (Close/VWAP, Open=VWAP, High, Low, Volume)
# VWAP is used as Close (best intra-day representative price).
# Open = VWAP (no separate open data in NSE daily bulletin).

PRICES_2026_07_21: dict[str, tuple] = {
    # Agricultural
    "EGAD":  (30.85, 30.85, 31.00, 30.00, 5391),
    "KUKZ":  (427.75, 427.75, 429.50, 423.00, 432),
    "KAPC":  (343.50, 343.50, 350.00, 338.00, 6444),
    "SASN":  (23.50, 23.50, 24.25, 23.30, 14784),
    "WTK":   (173.00, 173.00, 174.75, 170.25, 21080),
    # Automobiles
    "CGEN":  (124.00, 124.00, 125.00, 120.00, 2984),
    # Banking
    "ABSA":  (33.10, 33.10, 33.95, 32.85, 381641),
    "BKG":   (57.00, 57.00, 59.00, 56.00, 7621),
    "DTK":   (146.50, 146.50, 147.75, 146.25, 580145),
    "EQTY":  (86.50, 86.50, 87.00, 86.25, 4383092),
    "FMLY":  (26.05, 26.05, 27.00, 25.00, 563385),
    "HFCK":  (11.85, 11.85, 12.00, 11.60, 906841),
    "IMH":   (68.25, 68.25, 69.00, 67.75, 67006),
    "KCB":   (81.25, 81.25, 82.00, 80.00, 2070328),
    "NCBA":  (89.25, 89.25, 92.00, 88.50, 93488),
    "SBIC":  (291.50, 291.50, 296.00, 279.50, 3764),
    "SCBK":  (336.50, 336.50, 344.00, 333.25, 14380),
    "COOP":  (35.05, 35.05, 35.30, 34.50, 242631),
    # Commercial & Services
    "EVRD":  (1.07, 1.07, 1.09, 1.04, 134832),
    "XPRS":  (6.94, 6.94, 7.10, 6.70, 1688),
    "HAFR":  (1.12, 1.12, 1.23, 1.08, 1879242),
    "KQ":    (5.56, 5.56, 5.78, 5.48, 432017),
    "LKL":   (2.63, 2.63, 2.88, 2.55, 15582),
    "NBV":   (1.37, 1.37, 1.40, 1.32, 23666),
    "NMG":   (12.75, 12.75, 12.80, 12.60, 9502),
    "SMER":  (16.55, 16.55, 17.00, 16.00, 16679),
    "SGL":   (6.12, 6.12, 6.18, 6.00, 784),
    "TPSE":  (15.05, 15.05, 15.40, 14.80, 16955),
    "UCHM":  (1.70, 1.70, 1.70, 1.67, 124718),
    "SCAN":  (2.07, 2.07, 2.15, 2.00, 192015),
    # Construction & Allied
    "CRWN":  (59.50, 59.50, 60.00, 57.25, 2861),
    "PORT":  (111.50, 111.50, 115.00, 107.50, 2638),
    # Energy & Petroleum
    "KEGN":  (10.40, 10.40, 10.50, 10.30, 1103164),
    "KPC":   (9.12, 9.12, 9.20, 9.02, 372601),
    "KPLC":  (19.75, 19.75, 20.00, 19.65, 2672174),
    "TOTL":  (44.00, 44.00, 44.50, 43.00, 16149),
    "UMME":  (7.18, 7.18, 7.42, 7.00, 89989),
    # Insurance
    "BRIT":  (20.10, 20.10, 21.90, 18.05, 263219),
    "CIC":   (4.56, 4.56, 4.60, 4.53, 91584),
    "JUB":   (379.50, 379.50, 380.00, 373.00, 1325),
    "KNRE":  (3.51, 3.51, 3.59, 3.46, 926528),
    "LBTY":  (9.28, 9.28, 9.50, 8.98, 15237),
    "SLAM":  (8.72, 8.72, 8.80, 8.52, 38834),
    # Investment
    "CTUM":  (14.85, 14.85, 15.20, 14.60, 39695),
    "KURV":  (1460.00, 1460.00, 1460.00, 1460.00, 13),
    "OCH":   (7.00, 7.00, 7.08, 6.90, 32857),
    "NSE":   (23.95, 23.95, 24.00, 23.50, 103636),
    # Manufacturing
    "BOC":   (172.25, 172.25, 174.00, 171.00, 382),
    "BAT":   (579.00, 579.00, 581.00, 575.00, 11790),
    "CARB":  (36.10, 36.10, 36.50, 36.00, 15189),
    "EABL":  (266.00, 266.00, 270.00, 265.00, 60069),
    "AMAC":  (113.50, 113.50, 116.00, 107.00, 317),
    "UNGA":  (29.00, 29.00, 29.50, 27.75, 13521),
    # Telecom
    "SCOM":  (35.05, 35.05, 35.50, 35.00, 5119845),
    # ETF
    "GLD":   (4940.00, 4940.00, 5245.00, 4910.00, 55),
    "SMWF":  (933.00, 933.00, 943.00, 930.00, 226),
    # TRFC: suspended — no trading data for July 21
    # LIMT: no trading data confirmed for July 21
}

PRICES_2026_07_22: dict[str, tuple] = {
    # Agricultural
    "EGAD":  (29.70, 29.70, 31.00, 29.00, 211),
    "KUKZ":  (426.50, 426.50, 435.00, 425.00, 365),
    "KAPC":  (346.25, 346.25, 350.00, 340.00, 7997),
    "LIMT":  (514.50, 514.50, 530.00, 495.00, 20),   # VWAP estimated as midpoint; 538 in PREV col
    "SASN":  (23.50, 23.50, 25.00, 23.00, 4326),
    "WTK":   (173.75, 173.75, 175.00, 172.00, 15728),
    # Automobiles
    "CGEN":  (125.75, 125.75, 128.00, 123.00, 3618),
    # Banking
    "ABSA":  (33.05, 33.05, 33.45, 32.80, 168329),
    "BKG":   (57.00, 57.00, 61.00, 56.00, 13200),
    "DTK":   (149.50, 149.50, 150.00, 146.50, 35192),
    "EQTY":  (87.00, 87.00, 87.00, 86.25, 112434),
    "FMLY":  (26.65, 26.65, 27.50, 26.00, 639619),
    "HFCK":  (11.95, 11.95, 12.00, 11.85, 1046382),
    "IMH":   (67.75, 67.75, 68.25, 67.25, 55864),
    "KCB":   (81.25, 81.25, 82.50, 80.00, 1370972),
    "NCBA":  (89.25, 89.25, 91.75, 88.50, 10720),
    "SBIC":  (291.75, 291.75, 293.00, 285.50, 4038),
    "SCBK":  (340.25, 340.25, 344.00, 336.50, 29861),
    "COOP":  (34.95, 34.95, 35.10, 34.80, 164695),
    # Commercial & Services
    "EVRD":  (1.03, 1.03, 1.07, 1.01, 316207),
    "XPRS":  (7.06, 7.06, 7.10, 6.94, 1777),
    "HAFR":  (1.08, 1.08, 1.21, 1.05, 2488172),
    "KQ":    (5.56, 5.56, 5.80, 5.48, 57142),
    "LKL":   (2.65, 2.65, 2.85, 2.53, 25188),
    "NBV":   (1.32, 1.32, 1.37, 1.30, 21648),
    "NMG":   (12.75, 12.75, 12.80, 12.10, 19267),
    "SMER":  (16.55, 16.55, 18.20, 15.60, 73556),
    "SGL":   (6.12, 6.12, 6.12, 6.00, 256),
    "TPSE":  (15.10, 15.10, 15.50, 14.75, 57142),
    "UCHM":  (1.70, 1.70, 1.70, 1.63, 134727),
    "SCAN":  (2.07, 2.07, 2.15, 1.89, 16903),
    # Construction & Allied
    "CRWN":  (59.50, 59.50, 59.75, 57.50, 2861),
    "PORT":  (105.00, 105.00, 112.00, 100.50, 2751),
    # Energy & Petroleum
    "KEGN":  (10.35, 10.35, 10.50, 10.35, 2752367),
    "KPC":   (9.14, 9.14, 9.20, 9.30, 331173),
    "KPLC":  (20.00, 20.00, 20.00, 19.80, 870345),
    "TOTL":  (43.95, 43.95, 45.90, 43.50, 24780),
    "UMME":  (7.18, 7.18, 7.46, 6.90, 89309),
    # Insurance
    "BRIT":  (18.15, 18.15, 19.35, 18.10, 203413),
    "CIC":   (4.62, 4.62, 4.70, 4.53, 171970),
    "JUB":   (375.75, 375.75, 380.00, 373.00, 2753),
    "KNRE":  (3.51, 3.51, 3.59, 3.46, 937432),
    "LBTY":  (9.18, 9.18, 9.50, 8.96, 14044),
    "SLAM":  (8.82, 8.82, 9.00, 8.70, 41958),
    # Investment
    "CTUM":  (14.90, 14.90, 15.20, 14.60, 40265),
    "HAFR":  (1.08, 1.08, 1.21, 1.05, 2488172),   # also appears in commercial
    "KURV":  (1490.00, 1490.00, 1490.00, 1490.00, 13),
    "OCH":   (6.64, 6.64, 7.30, 6.32, 2124),
    "NSE":   (23.85, 23.85, 24.00, 23.80, 60870),
    # Manufacturing
    "BOC":   (170.50, 170.50, 172.00, 168.50, 1456),
    "BAT":   (579.00, 579.00, 582.00, 570.00, 7814),
    "CARB":  (36.10, 36.10, 36.30, 35.65, 40114),
    "EABL":  (269.50, 269.50, 270.00, 268.00, 4192),
    "AMAC":  (113.50, 113.50, 105.00, 107.00, 76),
    "UNGA":  (29.85, 29.85, 30.35, 29.00, 2643),
    # Telecom
    "SCOM":  (35.30, 35.30, 35.50, 35.00, 2129469),
    # REIT
    "TRFC":  (1.23, 1.23, 1.23, 1.23, 1000),  # Trific Green I-REIT traded on Jul 22
    # ETF
    "GLD":   (4985.00, 4985.00, 5140.00, 4970.00, 643),
    "SMWF":  (933.00, 933.00, 944.00, 931.00, 83),
}

DATE_PRICES = {
    "2026-07-21": PRICES_2026_07_21,
    "2026-07-22": PRICES_2026_07_22,
}


# ── Firebase upload helpers ───────────────────────────────────────────────────

def _safe_name(ticker: str) -> str:
    return ticker.replace(".", "_")


def _load_local_csv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
        df.columns = [c.strip().title() for c in df.columns]
        date_col = next((c for c in df.columns if "date" in c.lower()), None)
        if date_col is None:
            return None
        df[date_col] = pd.to_datetime(df[date_col], dayfirst=False, format="mixed")
        df = df.set_index(date_col).sort_index()
        df.index.name = "Date"
        return df
    except Exception as exc:
        log.warning("Could not load %s: %s", path, exc)
        return None


def apply_backfill(dry_run: bool = False) -> None:
    if not dry_run:
        get_db()

    companies   = load_companies()
    base_to_safe = {
        (s[:-3] if s.endswith("_NR") else s): s
        for s in (_safe_name(c["ticker"]) for c in companies)
    }

    CSVS_TMP.mkdir(parents=True, exist_ok=True)

    total_updated = 0
    total_skipped = 0

    for date_str, prices in sorted(DATE_PRICES.items()):
        ts = pd.Timestamp(date_str)
        log.info("=== %s (%d companies with data) ===", date_str, len(prices))

        updated_this_date = 0
        for base, (close, open_, high, low, volume) in prices.items():
            safe = base_to_safe.get(base)
            if not safe:
                log.debug("No company entry for base=%s — skipping", base)
                continue

            storage_path = f"data/cleaned/{safe}_cleaned.csv"
            local_path   = CSVS_TMP / f"{safe}_cleaned.csv"

            if dry_run:
                log.info("[DRY-RUN] %s  %s  close=%.4f  vol=%d", safe, date_str, close, volume)
                updated_this_date += 1
                continue

            in_storage = download_model_from_storage(storage_path, str(local_path))

            existing_df: pd.DataFrame | None = None
            if local_path.exists():
                existing_df = _load_local_csv(local_path)
                if existing_df is not None and "Is_Stale" in existing_df.columns:
                    existing_df = existing_df[existing_df["Is_Stale"] != 1]

            # Skip if this date already has a real row (Volume > 0)
            if existing_df is not None and ts in existing_df.index:
                row = existing_df.loc[ts]
                if float(row.get("Volume", 0)) > 0:
                    log.debug("%s: %s already has data (close=%.4f) — skip", safe, date_str, float(row["Close"]))
                    total_skipped += 1
                    continue
                existing_df = existing_df.drop(index=ts)

            new_row = pd.DataFrame(
                [{"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume}],
                index=pd.DatetimeIndex([ts], name="Date"),
            )

            if existing_df is not None and not existing_df.empty:
                keep = [c for c in new_row.columns if c in existing_df.columns]
                combined = pd.concat([existing_df[[c for c in keep if c in existing_df.columns]], new_row[keep]]).sort_index()
            else:
                combined = new_row.sort_index()

            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined[combined.index.dayofweek < 5]

            combined.to_csv(local_path)
            upload_model_to_storage(str(local_path), storage_path)

            log.info("%s  %s  close=%.4f  vol=%d  → uploaded", safe, date_str, close, volume)
            updated_this_date += 1

        total_updated += updated_this_date
        log.info("%s: updated %d companies", date_str, updated_this_date)

    log.info("=== Done: %d updates, %d already-present skips ===", total_updated, total_skipped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply NSE PDF backfill for July 21–22, 2026")
    parser.add_argument("--dry-run", action="store_true", help="Preview without touching Firebase")
    args = parser.parse_args()
    apply_backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
