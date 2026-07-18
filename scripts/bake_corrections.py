"""
One-time script: apply the archive-overlay decimal correction to all cleaned CSVs
and save the corrected values back in place. Run before first production deploy.

Usage:  python scripts/bake_corrections.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pipeline"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from config import DATA_CLEANED

# ── Inline the correction logic from app.py ───────────────────────────────────
_ARCHIVE_DIR = Path(r"C:\Users\moeng\Downloads\archive")

def _normalise_cols(df):
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns={c: c.lower() for c in df.columns})
    return df.rename(columns={"date": "Date", "code": "Code",
                               "day price": "Day Price", "volume": "Volume"})

def _build_master():
    frames = []
    def _load(path):
        try:
            raw = pd.read_csv(path, dtype=str)
            df  = _normalise_cols(raw)
            if "Code" not in df.columns or "Day Price" not in df.columns:
                return
            df["Code"] = df["Code"].str.strip()
            df["_dt"] = pd.to_datetime(df["Date"].str.strip(), dayfirst=False,
                                        format="mixed", errors="coerce")
            df = df.dropna(subset=["_dt"])
            df["Close"] = pd.to_numeric(
                df["Day Price"].str.replace(",", "", regex=False).str.strip(), errors="coerce")
            df["Volume"] = pd.to_numeric(
                df["Volume"].str.replace(",", "", regex=False).str.strip(), errors="coerce"
            ) if "Volume" in df.columns else np.nan
            df = df[df["Close"] > 0].dropna(subset=["Close"])
            frames.append(df[["_dt", "Code", "Close", "Volume"]])
        except Exception:
            pass

    if _ARCHIVE_DIR.exists():
        for p in sorted(_ARCHIVE_DIR.glob("NSE_data_all_stocks_????.csv")):
            _load(p)
        for p in sorted(_ARCHIVE_DIR.glob("NSE_patch_*.csv")):
            _load(p)

    if not frames:
        return pd.DataFrame(columns=["_dt", "Code", "Close", "Volume"])
    m = pd.concat(frames, ignore_index=True).sort_values(["Code", "_dt"])
    return m.drop_duplicates(subset=["_dt", "Code"], keep="last")


def _get_archive(master, code):
    if master.empty or code not in set(master["Code"]):
        return None
    rows = master[master["Code"] == code].copy()
    df = pd.DataFrame({"Close": rows["Close"].values, "Volume": rows["Volume"].values},
                      index=rows["_dt"])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df if len(df) >= 5 else None


def _apply_correction(df_raw, arc):
    """Overlay archive prices onto cleaned CSV, interpolate orphan spikes."""
    df = df_raw.copy()
    if arc is None or arc.empty or "Close" not in arc.columns:
        return df
    raw_close = df["Close"].copy()
    arc_close = arc["Close"].reindex(df.index)
    valid = arc_close.notna()
    if not valid.any():
        return df
    df.loc[valid, "Close"] = arc_close[valid]
    ratio = arc_close.div(raw_close.replace(0, np.nan)).fillna(1.0).clip(1e-4, 1e4)
    for col in ["Open", "High", "Low"]:
        if col in df.columns:
            df.loc[valid, col] = (df[col].mul(ratio)).loc[valid]
    if not valid.all():
        close = df["Close"].astype(float)
        log_close = np.log(close.clip(lower=1e-9))
        log_med = float(np.median(log_close[valid]))
        orphan = ~valid & (np.abs(log_close - log_med) > np.log(20))
        if orphan.any():
            for col in ["Close", "Open", "High", "Low"]:
                if col in df.columns:
                    s = df[col].astype(float).copy()
                    s[orphan] = np.nan
                    s = s.interpolate(method="time").ffill().bfill()
                    df[col] = s
    return df


def main():
    print("Building archive master…")
    master = _build_master()
    if master.empty:
        print("Archive not found or empty — no corrections to apply.")
        print("CSVs already contain their original values.")
        return

    codes = set(master["Code"].unique())
    print(f"Archive loaded: {len(master):,} rows, {len(codes)} companies.")

    files = list(DATA_CLEANED.glob("*_NR_cleaned.csv"))
    print(f"Processing {len(files)} cleaned CSVs…")

    fixed = skipped = 0
    for p in sorted(files):
        ticker = p.stem.replace("_cleaned", "").replace("_", ".", 1)
        code = ticker.split(".")[0].upper()
        try:
            df_raw = pd.read_csv(p, index_col="Date", parse_dates=True)
            arc = _get_archive(master, code)
            df_fixed = _apply_correction(df_raw, arc)
            df_fixed.to_csv(p)
            if arc is not None:
                fixed += 1
                print(f"  OK {ticker}")
            else:
                skipped += 1
        except Exception as e:
            print(f"  FAIL {ticker}: {e}")

    print(f"Done. {fixed} corrected, {skipped} had no archive data.")


if __name__ == "__main__":
    main()
