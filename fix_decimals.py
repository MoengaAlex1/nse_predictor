"""Fix decimal-dropped OCR prices across all cleaned CSVs and RTDB."""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import firebase_admin
from firebase_admin import credentials, db as fdb

sys.path.insert(0, str(Path(__file__).parent))

sa_path = r"C:\Users\moeng\Downloads\nse-market-dashboard-firebase-adminsdk-fbsvc-68d525293a.json"
sa_dict = json.load(open(sa_path))
cred = credentials.Certificate(sa_dict)
firebase_admin.initialize_app(cred, {
    "databaseURL": "https://nse-market-dashboard-default-rtdb.firebaseio.com"
})
root_ref = fdb.reference("/")

COLS = ["Open", "High", "Low", "Close"]
THRESHOLD = 30   # spike must be >30x the column's own median
MAX_RATIO  = 15  # corrected value must be within 15x of median


def fix_column(series: pd.Series):
    pos = series[series > 0]
    if pos.empty:
        return series, []
    median = pos.median()
    if pd.isna(median) or median == 0:
        return series, []

    fixed = series.copy()
    bad_idx = []
    for i in range(len(series)):
        val = series.iloc[i]
        if pd.isna(val) or val <= 0:
            continue
        if val > median * THRESHOLD:
            corrected = val / 100
            if 0.05 < corrected / median < MAX_RATIO:
                fixed.iloc[i] = round(corrected, 4)
                bad_idx.append(i)
    return fixed, bad_idx


data_dir = Path("data/cleaned")
total_dates = 0

for csv_path in sorted(data_dir.glob("*_NR_cleaned.csv")):
    try:
        df = pd.read_csv(csv_path, parse_dates=["Date"], index_col="Date").sort_index()
    except Exception as e:
        print(f"SKIP {csv_path.name}: {e}")
        continue

    short = csv_path.stem.replace("_NR_cleaned", "").split("_")[0]
    changed_dates = set()

    for col in COLS:
        if col not in df.columns:
            continue
        fixed_col, bad_idx = fix_column(df[col])
        if bad_idx:
            df[col] = fixed_col
            for i in bad_idx:
                changed_dates.add(df.index[i].strftime("%Y-%m-%d"))

    if not changed_dates:
        continue

    print(f"{short}: {len(changed_dates)} dates fixed")
    df.index.name = "Date"
    df.to_csv(csv_path)
    total_dates += len(changed_dates)

    # Push all corrected dates to RTDB as a single batch
    batch = {}
    for date_str in changed_dates:
        mask = df.index.strftime("%Y-%m-%d") == date_str
        if not mask.any():
            continue
        r = df[mask].iloc[0]

        existing = fdb.reference(f"prices/{short}/{date_str}").get() or {}
        node = dict(existing)
        for src, dst in [("Open","o"),("High","h"),("Low","l"),("Close","c")]:
            if src in df.columns and pd.notna(r[src]):
                node[dst] = round(float(r[src]), 4)
        batch[f"prices/{short}/{date_str}"] = node

    if batch:
        root_ref.update(batch)

print(f"\nAll done. Total dates corrected: {total_dates}")
