"""Debug companies still dirty after repair — show date ranges of bad rows."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from app import _ARCHIVE_MASTER, _ARCHIVE_CODES, _repair_decimal_errors

WARN_RATIO = 15.0
TARGETS = ["0", "AMAC", "CARB", "CMC", "DCON", "HAFR", "HFCK-R", "ICDC",
           "KCB-R", "KPLC", "KQ", "KUKZ", "MSC", "SASN", "UCHM"]

for code in TARGETS:
    rows = _ARCHIVE_MASTER[_ARCHIVE_MASTER["Code"] == code].sort_values("_dt")
    if rows.empty:
        print(f"{code}: NOT IN ARCHIVE\n")
        continue

    raw = rows["Close"].values.astype(float)
    valid_raw = raw[(raw > 0) & ~np.isnan(raw)]
    if len(valid_raw) < 5:
        continue

    fixed_vals = _repair_decimal_errors(pd.Series(raw, index=rows.index))
    dates      = rows["_dt"].values

    log_fixed  = np.log10(fixed_vals.values[(fixed_vals.values > 0)])
    log_med    = float(np.median(log_fixed))
    med_price  = 10 ** log_med

    # Identify remaining dirty rows
    mask_dirty = np.abs(np.log10(np.maximum(fixed_vals.values, 1e-9)) - log_med) > np.log10(WARN_RATIO)
    dirty_dates = pd.DatetimeIndex(pd.to_datetime(dates[mask_dirty]))
    dirty_prices_fixed = fixed_vals.values[mask_dirty]
    dirty_prices_raw   = raw[mask_dirty]

    print(f"{'='*70}")
    print(f"{code}: {len(rows)} rows total, {mask_dirty.sum()} still dirty after repair")
    print(f"  Median price (post-repair): {med_price:.2f} KES")
    print(f"  Raw price range: {valid_raw.min():.2f} – {valid_raw.max():.2f} KES")
    print(f"  Fixed price range: {fixed_vals[fixed_vals>0].min():.2f} – {fixed_vals[fixed_vals>0].max():.2f} KES")
    print(f"  Year distribution of dirty rows:")
    if len(dirty_dates) > 0:
        year_counts = pd.Series(dirty_dates.year).value_counts().sort_index()
        for yr, cnt in year_counts.items():
            # Show ratio for that year's dirty rows
            yr_mask = np.array(dirty_dates.year == yr)
            yr_prices_fixed = dirty_prices_fixed[yr_mask]
            yr_prices_raw   = dirty_prices_raw[yr_mask]
            ratios = [f"{p:.2f}→{f:.2f}({p/f:.0f}x)" if f>0.001 else f"{p:.2f}"
                      for p, f in zip(yr_prices_raw[:3], yr_prices_fixed[:3])]
            print(f"    {yr}: {cnt} rows  sample={ratios}")
    print()
