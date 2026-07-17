"""One-shot outlier diagnostic across all NSE archive years."""
import pandas as pd
import numpy as np
from pathlib import Path

archive_dir = Path(r"C:\Users\moeng\Downloads\archive")

frames = []
for path in sorted(archive_dir.glob("NSE_data_all_stocks_????.csv")):
    try:
        df = pd.read_csv(path, dtype=str)
        df.columns = [c.strip() for c in df.columns]
        # Normalize column names (older files use DATE/CODE)
        col_map = {c: c.lower() for c in df.columns}
        df = df.rename(columns=col_map)
        date_col  = next((c for c in df.columns if c == "date"), None)
        code_col  = next((c for c in df.columns if c == "code"), None)
        price_col = next((c for c in df.columns if c == "day price"), None)
        if not all([date_col, code_col, price_col]):
            print(f"SKIP {path.name}: cols={list(df.columns)[:5]}")
            continue
        df["_dt"]  = pd.to_datetime(df[date_col].str.strip(), dayfirst=False, format="mixed", errors="coerce")
        df["price"] = pd.to_numeric(df[price_col].astype(str).str.replace(",","").str.strip(), errors="coerce")
        df["Code"] = df[code_col].str.strip()
        df["year"] = int(path.stem[-4:])
        frames.append(df[["_dt","Code","price","year"]].dropna(subset=["_dt","price"]))
    except Exception as e:
        print(f"ERR {path.name}: {e}")

all_data = pd.concat(frames, ignore_index=True)
all_data = all_data[all_data["price"] > 0].copy()
print(f"Loaded {len(all_data)} rows, {all_data['Code'].nunique()} companies")
print()

LOG_THRESHOLD = np.log10(50)  # flag values 50x+ from global median

print("COMPANIES WITH SIGNIFICANT OUTLIERS (>50x from global median):")
print("-" * 90)
total_outlier_rows = 0
for code in sorted(all_data["Code"].unique()):
    grp = all_data[all_data["Code"] == code].sort_values("_dt")
    prices = grp["price"].values
    if len(prices) < 10:
        continue
    log_prices = np.log10(prices)
    log_med = np.median(log_prices)
    deviations = np.abs(log_prices - log_med)
    outlier_mask = deviations > LOG_THRESHOLD
    n_outliers = outlier_mask.sum()
    if n_outliers == 0:
        continue
    total_outlier_rows += n_outliers
    max_ratio = 10 ** deviations[outlier_mask].max()
    # Show sample bad rows
    bad_rows = grp[outlier_mask].copy()
    bad_rows["ratio"] = (bad_rows["price"] / (10 ** log_med)).round(1)
    print(f"  {code:6s}  med={10**log_med:8.2f} KES  outlier_rows={n_outliers:4d}  max_ratio={max_ratio:6.0f}x")
    # Show up to 5 example bad rows
    sample = bad_rows.head(5)[["_dt","price","ratio","year"]]
    for _, row in sample.iterrows():
        print(f"            {row['_dt'].date()}  price={row['price']:10.2f}  ratio={row['ratio']:6.1f}x  year={row['year']}")

print()
print(f"TOTAL OUTLIER ROWS: {total_outlier_rows}")
