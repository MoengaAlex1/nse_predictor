"""Verify the trailing-window decimal-repair across all NSE companies."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Use app.py helpers directly
sys.path.insert(0, str(Path(__file__).parent.parent))
from app import _ARCHIVE_MASTER, _ARCHIVE_CODES, _repair_decimal_errors

WARN_RATIO = 22.0   # just above the 20x repair threshold — any residual is legitimate historical price

print(f"Archive: {len(_ARCHIVE_MASTER):,} rows, {len(_ARCHIVE_CODES)} companies\n")

flagged = []
for code in sorted(_ARCHIVE_CODES):
    rows = _ARCHIVE_MASTER[_ARCHIVE_MASTER["Code"] == code].sort_values("_dt")
    raw   = rows["Close"].values.astype(float)
    raw   = raw[(raw > 0) & ~np.isnan(raw)]
    if len(raw) < 10:
        continue

    fixed = _repair_decimal_errors(pd.Series(raw)).values

    log_fixed = np.log10(fixed[(fixed > 0)])
    log_med   = np.median(log_fixed)
    max_ratio = float(10 ** np.max(np.abs(log_fixed - log_med)))
    n_before  = int(np.sum(np.abs(np.log10(raw[(raw > 0)]) - np.median(np.log10(raw[(raw > 0)]))) > np.log10(WARN_RATIO)))
    n_after   = int(np.sum(np.abs(log_fixed - log_med) > np.log10(WARN_RATIO)))

    if n_before > 0 or n_after > 0:
        status = "CLEAN" if n_after == 0 else "STILL_DIRTY"
        flagged.append((code, n_before, n_after, round(10**log_med, 2), round(max_ratio, 1), status))

print(f"{'Code':6s}  {'Before':>6}  {'After':>5}  {'Median':>8}  {'MaxRatio':>10}  Status")
print("-" * 70)
still_dirty = 0
for code, nb, na, med, mx, status in flagged:
    print(f"{code:6s}  {nb:6d}  {na:5d}  {med:8.2f} KES  {mx:8.1f}x  {status}")
    if status == "STILL_DIRTY":
        still_dirty += 1

print()
print(f"Companies with outliers BEFORE repair: {len(flagged)}")
print(f"Companies STILL dirty after repair:    {still_dirty}")
if still_dirty == 0:
    print("\nAll outliers resolved.")
else:
    print("\nSome companies still have outliers — investigate above.")
