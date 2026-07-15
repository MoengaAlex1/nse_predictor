"""
Run the full prediction pipeline (feature engineering + model training + dashboard)
for every NSE ticker that has a cleaned CSV available.

Usage:
    python run_all.py                  # all 5 tickers
    python run_all.py EQTY.NR KCB.NR  # specific tickers only
"""
import sys
import io
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from main import run
from config import NSE_TICKERS, DEFAULT_INVESTMENT, START_DATE, DATA_CLEANED


def main(tickers: list = None):
    tickers = tickers or NSE_TICKERS

    # Only run tickers that have a cleaned CSV
    runnable = [
        t for t in tickers
        if (DATA_CLEANED / f"{t.replace('.', '_')}_cleaned.csv").exists()
    ]
    skipped = [t for t in tickers if t not in runnable]

    if skipped:
        print(f"\n[SKIP] No cleaned CSV for: {skipped}")
        print("       Run `python run_pipeline.py` first to clean raw data.\n")

    if not runnable:
        print("Nothing to run.")
        return {}

    print(f"\nRunning pipeline for {len(runnable)} ticker(s): {runnable}")

    results = {}
    for ticker in runnable:
        print(f"\n{'#'*60}")
        print(f"  {ticker}")
        print(f"{'#'*60}")
        try:
            results[ticker] = run(
                ticker=ticker,
                investment=DEFAULT_INVESTMENT,
                start=START_DATE,
            )
        except Exception as e:
            print(f"\n[ERROR] {ticker}: {e}")
            results[ticker] = {"error": str(e)}

    # ── Final summary ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  ALL TICKERS — SIGNAL SUMMARY")
    print(f"{'='*60}")
    for t, res in results.items():
        if "error" in res:
            print(f"  {t:<12}  ERROR: {res['error']}")
        else:
            sig     = res.get("signal", "?")
            ra_sig  = res.get("risk_adjusted_signal", "?")
            chg     = res.get("predicted_change_pct", 0)
            price   = res.get("current_price_KES", 0)
            print(
                f"  {t:<12}  {sig:<5}  (risk-adj: {ra_sig:<5})  "
                f"KES {price:>7.2f}  Δ {chg:+.2f}%"
            )
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    tickers = sys.argv[1:] or None
    main(tickers)
