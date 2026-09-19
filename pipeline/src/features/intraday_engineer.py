"""Intraday feature computer.

Turns a list of intraday `{time: "HH:MM", price: float}` snapshots (as
persisted by push_intraday_prices.py under companies/{doc}.intraday_today)
into a compact dict of ML-ready features.

Design constraints
------------------
* We only have intraday history for a few weeks — the daily-bar models
  train on years back. So intraday features are treated as an OVERLAY:
  they augment the daily prediction rather than replacing it.
* Every feature is nullable. Callers must handle None (e.g. weekends,
  fresh listings with no snapshots yet).
* Names are stable — they land in Firestore snapshots AND in the XGBoost
  feature-column list, so renaming them is a breaking change.
"""

from __future__ import annotations

from statistics import mean
from typing import Sequence


# Neutral placeholder values for use in historical training rows that
# lack intraday data. Zero (or midpoint 0.5 for percentiles) means
# "no information" — the ML model can learn to ignore them.
NEUTRAL_INTRADAY: dict[str, float] = {
    "intra_snapshots":              0.0,
    "intra_opening_drift_pct":      0.0,
    "intra_vs_prev_close_pct":      0.0,
    "intra_range_pct":              0.0,
    "intra_position_in_range":      0.5,
    "intra_last_hour_momentum_pct": 0.0,
    "intra_last_30m_momentum_pct":  0.0,
    "intra_direction_bias":         0.0,
}

# Assume ~15-min cadence (28 snapshots per 6h45m trading day). Windows in
# COUNT rather than minutes so the module doesn't care about the exact
# cadence. If we bump to 10-min later, tune LAST_HOUR_SNAPS accordingly.
LAST_HOUR_SNAPS = 4     # 4 × 15min ≈ last hour
LAST_30M_SNAPS  = 2     # 2 × 15min ≈ last 30 minutes


def compute_intraday_features(
    points: Sequence[dict] | None,
    prev_close: float | None = None,
) -> dict[str, float | None]:
    """Derive ML-ready features from today's intraday snapshot list.

    Returns a dict with every key from NEUTRAL_INTRADAY. Fields are None
    when there are fewer than 2 snapshots (nothing to compute); zero /
    neutral values in NEUTRAL_INTRADAY are what training-row fillers use.

    Parameters
    ----------
    points:
        Ordered list of {time, price} dicts (as stored in
        companies/{doc}.intraday_today). Empty list, None, or malformed
        rows are tolerated and return all-None output.
    prev_close:
        Yesterday's close. Required for `intra_vs_prev_close_pct` and
        `intra_opening_drift_pct`. Pass None if unknown; those fields
        will be None too.
    """
    empty: dict[str, float | None] = {k: None for k in NEUTRAL_INTRADAY}

    if not points:
        return empty

    prices: list[float] = []
    for p in points:
        if not isinstance(p, dict):
            continue
        v = p.get("price")
        if isinstance(v, (int, float)) and v > 0:
            prices.append(float(v))

    if len(prices) < 2:
        return {**empty, "intra_snapshots": float(len(prices))}

    opening = prices[0]
    current = prices[-1]
    hi = max(prices)
    lo = min(prices)
    span = hi - lo

    # Opening drift: current vs the day's first snapshot. Complementary to
    # daily gap (which is opening vs previous close) — this tracks how the
    # session has evolved since the opening bell.
    opening_drift = _pct(current - opening, opening)

    vs_prev = _pct(current - prev_close, prev_close) if prev_close is not None else None

    range_pct = _pct(span, opening) if opening > 0 else None
    position_in_range = (current - lo) / span if span > 0 else 0.5

    # Momentum windows — anchor to the earliest snapshot inside the window
    # so a shorter session still yields a value.
    def _momentum(window: int) -> float | None:
        anchor = prices[-min(window + 1, len(prices))]
        if anchor <= 0:
            return None
        return _pct(current - anchor, anchor)

    last_hour = _momentum(LAST_HOUR_SNAPS)
    last_30m  = _momentum(LAST_30M_SNAPS)

    # Direction bias: fraction of consecutive-diff moves that were positive
    # minus fraction that were negative. Range: -1 (all-down) → +1 (all-up).
    diffs = [prices[i + 1] - prices[i] for i in range(len(prices) - 1)]
    ups   = sum(1 for d in diffs if d > 0)
    downs = sum(1 for d in diffs if d < 0)
    total = ups + downs
    direction_bias = (ups - downs) / total if total > 0 else 0.0

    return {
        "intra_snapshots":              float(len(prices)),
        "intra_opening_drift_pct":      opening_drift,
        "intra_vs_prev_close_pct":      vs_prev,
        "intra_range_pct":              range_pct,
        "intra_position_in_range":      position_in_range,
        "intra_last_hour_momentum_pct": last_hour,
        "intra_last_30m_momentum_pct":  last_30m,
        "intra_direction_bias":         direction_bias,
    }


def _pct(numer: float, denom: float | None) -> float | None:
    """Percent as a float, or None when the denominator is missing/zero."""
    if denom is None or denom <= 0:
        return None
    return numer / denom * 100.0


def intraday_features_or_neutral(
    points: Sequence[dict] | None,
    prev_close: float | None = None,
) -> dict[str, float]:
    """Like compute_intraday_features but returns NEUTRAL_INTRADAY values
    instead of None for missing fields. Use this when feeding features
    into the XGBoost feature matrix (which can't accept NaN placeholders
    silently — RFE and pct_change chains break)."""
    computed = compute_intraday_features(points, prev_close)
    return {k: (v if v is not None else NEUTRAL_INTRADAY[k])
            for k, v in computed.items()}
