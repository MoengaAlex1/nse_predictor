"""
scale_guard.py — ticker-agnostic OCR/decimal-scale error detector and corrector.

Every existing scale-fix in this pipeline (scrape_nse_pdf.py's _fix_scale_vs_prev,
scrape_nse_daily_prices.py's ad hoc "if close > high * 10" check) anchors against
a prev_close pulled from the *same OCR'd PDF line* as the price being checked.
That is blind to the failure mode where OCR misreads an entire row uniformly —
High, Low, Close, and PrevClose all shifted by the same factor — because every
field still agrees with its neighbors on the same (wrong) line.

This module anchors instead against the ticker's own recent real-trade history
(a robust median, not just yesterday's row), which is what actually catches it:
a whole line shifted 100x still won't match months of real trading history.

Design rules (apply to every ticker identically — no per-company hardcoding):
  - Only correct when a SINGLE scale factor, applied uniformly to Open/High/
    Low/Close, both (a) lands the row within a sane band of the historical
    reference AND (b) produces an internally valid OHLC relationship
    (Low <= Open, Close <= High).
  - If no factor satisfies both, or the row is already internally invalid
    even after the best-fitting factor, do NOT guess — quarantine it for
    manual review. Never invent or force a replacement price.
"""
from __future__ import annotations

from dataclasses import dataclass

# Deviation from the historical reference at or beyond this ratio (or its
# reciprocal) is treated as a potential scale/OCR error worth investigating.
TRIGGER_RATIO = 3.0

# A candidate correction is accepted only if corrected_close / reference
# lands inside this band — i.e. within a plausible single-day move.
OK_BAND = (0.5, 2.0)

# Candidate scale factors to try, most-common-first. Each is tried as both
# a divisor (row is inflated) and a multiplier (row is deflated).
SCALE_FACTORS = (100, 10)


@dataclass(frozen=True)
class ScaleResult:
    status: str  # "ok" | "corrected" | "quarantine"
    open: float
    high: float
    low: float
    close: float
    factor: float = 1.0
    reason: str = ""


def median_reference(closes: list[float]) -> float | None:
    """Robust historical anchor: median of recent real-trade closes.

    Using the median (not just the single prior close) means one bad
    historical row can't itself become a false anchor.
    """
    values = sorted(c for c in closes if c and c > 0)
    if not values:
        return None
    n = len(values)
    mid = n // 2
    if n % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _ohlc_internally_valid(open_: float, high: float, low: float, close: float) -> bool:
    return low <= open_ <= high and low <= close <= high and low <= high


def check_scale(
    open_: float,
    high: float,
    low: float,
    close: float,
    reference_close: float | None,
    *,
    trigger_ratio: float = TRIGGER_RATIO,
    ok_band: tuple[float, float] = OK_BAND,
    factors: tuple[float, ...] = SCALE_FACTORS,
) -> ScaleResult:
    """Validate one day's OHLC row against a ticker's historical trend.

    Applicable to any ticker — the only inputs are the candidate row and a
    reference price derived from that same ticker's own history.
    """
    if reference_close is None or reference_close <= 0 or close <= 0:
        return ScaleResult("ok", open_, high, low, close, 1.0, "no historical reference available")

    ratio = close / reference_close
    lo, hi = ok_band

    if lo <= ratio <= hi:
        return ScaleResult("ok", open_, high, low, close, 1.0)

    if ratio < trigger_ratio and ratio > 1.0 / trigger_ratio:
        # Deviates from trend but not enough to treat as a scale error —
        # a real (if large) daily move. Leave it to spike/quarantine logic
        # elsewhere; this guard only handles clean decimal-shift errors.
        return ScaleResult("ok", open_, high, low, close, 1.0, "within normal deviation range")

    candidate_factors = factors if ratio >= trigger_ratio else tuple(1.0 / f for f in factors)

    for f in candidate_factors:
        c_open, c_high, c_low, c_close = (round(v / f, 4) for v in (open_, high, low, close))
        if not (lo <= c_close / reference_close <= hi):
            continue
        if not _ohlc_internally_valid(c_open, c_high, c_low, c_close):
            continue
        return ScaleResult(
            "corrected", c_open, c_high, c_low, c_close, f,
            f"uniform ÷{f:g} brought close in line with historical reference "
            f"({reference_close:.4f})",
        )

    return ScaleResult(
        "quarantine", open_, high, low, close, 1.0,
        f"close {close:.4f} deviates {ratio:.2f}x from historical reference "
        f"({reference_close:.4f}) and no scale factor resolves it cleanly",
    )
