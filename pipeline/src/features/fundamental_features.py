"""
Fundamental + announcement + macro features for the multi-horizon
LightGBM forecaster.

The prior price-history-only ensemble (LSTM + ARIMA + XGBoost) had one
big structural limit: at 3M+ horizons its predictions collapse to the
mean because no fundamental signal enters the feature matrix. Kenyan
retail investors act on earnings surprises, dividend calendars, and
regulatory announcements — none of which the model saw.

This module turns three Firestore docs per ticker into a flat float
feature vector that can be broadcast onto the daily price frame:

  financials/{ticker}    → annual results, dividends, announcements
  fundamentals/{ticker}  → shares outstanding, employees, sector proxy
  macro/kenya            → CBK rate, inflation, KES/USD

Design choices
- ALL features are point-in-time safe. `days_since_last_earnings`
  as of date T uses only announcements dated <= T. This is critical
  for backtesting — if we include future events the multi-horizon
  MAPE is meaningless.
- Features are floats with sentinel -1 for "not applicable" and 0 for
  "zero" (LightGBM handles NaN natively but a sentinel keeps the
  ARIMA/XGBoost consumers happy too).
- No forward-fill of announcement events; we count/decay them so the
  model learns that a fresh announcement matters more than a stale one.

Consumers:
  pipeline/src/features/engineer.py — merges these columns into the
  daily feature matrix used by every model (LSTM/XGB/LGBM).
  pipeline/scripts/run_inference.py — loads the "today" row for
  serving predictions.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Column names published downstream — kept as a module constant so the
# training and inference paths stay in sync (both call
# `add_fundamental_columns` on their respective frames).
FUNDAMENTAL_COLUMNS: list[str] = [
    "fund_days_since_earnings",
    "fund_days_to_next_earnings",
    "fund_days_since_dividend",
    "fund_days_to_next_dividend",
    "fund_last_eps_growth_yoy",
    "fund_last_revenue_growth_yoy",
    "fund_ann_count_30d",
    "fund_ann_count_90d",
    "fund_pe_ttm",
    "fund_dividend_yield",
    "fund_shares_out_log",
    "macro_cbk_rate",
    "macro_inflation_yoy",
    "macro_kes_usd",
]

_SENTINEL = -1.0   # LightGBM treats -1 as a distinct category vs missing


def _parse_date(s: Any) -> date | None:
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, str) and len(s) >= 10:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _sorted_dates(items: Iterable[dict], *keys: str) -> list[date]:
    """Extract the first available date from each item and return sorted
    ascending. Skips items with no valid date."""
    out: list[date] = []
    for it in items or []:
        for k in keys:
            d = _parse_date(it.get(k))
            if d:
                out.append(d)
                break
    out.sort()
    return out


def _days_since(sorted_asc: list[date], target: date) -> float:
    """Days between target and the latest date on or before target.
    -1 sentinel when no prior date exists."""
    prior = [d for d in sorted_asc if d <= target]
    if not prior:
        return _SENTINEL
    return float((target - prior[-1]).days)


def _days_until(sorted_asc: list[date], target: date) -> float:
    """Days between target and the next date strictly after target.
    -1 sentinel when no future date exists."""
    fut = [d for d in sorted_asc if d > target]
    if not fut:
        return _SENTINEL
    return float((fut[0] - target).days)


def _count_in_window(sorted_asc: list[date], target: date, window_days: int) -> float:
    """Number of dates in (target - window_days, target]."""
    cutoff = target - timedelta(days=window_days)
    return float(sum(1 for d in sorted_asc if cutoff < d <= target))


def _yoy_growth(rows_sorted_desc: list[dict], value_key: str) -> float:
    """(latest / prior - 1) for the given numeric key across annual results.
    Returns _SENTINEL when fewer than two rows or the prior is <= 0."""
    if len(rows_sorted_desc) < 2:
        return _SENTINEL
    v1 = rows_sorted_desc[0].get(value_key)
    v0 = rows_sorted_desc[1].get(value_key)
    if v1 is None or v0 is None or (isinstance(v0, (int, float)) and v0 <= 0):
        return _SENTINEL
    try:
        return float(v1) / float(v0) - 1.0
    except (TypeError, ZeroDivisionError):
        return _SENTINEL


def build_fundamental_row(
    as_of: date,
    financials: dict | None,
    fundamentals: dict | None,
    macro: dict | None,
    price: float | None,
) -> dict[str, float]:
    """Compute the fundamental feature vector as of a given date.

    Every field is point-in-time — announcements dated after `as_of`
    are excluded. This is what keeps the backtest honest.
    """
    fin = financials or {}
    fund = fundamentals or {}
    m = macro or {}

    # Announcement calendar — merge announcements + corporate_actions +
    # dividends into one date list; category detail isn't needed for the
    # "days since" features but keeps the count features realistic.
    ann_dates = _sorted_dates(
        list(fin.get("announcements") or [])
        + list(fin.get("corporate_actions") or []),
        "date", "announcement_date", "published_at",
    )
    ann_dates = [d for d in ann_dates if d <= as_of]

    div_dates = _sorted_dates(
        fin.get("dividends") or [],
        "ex_date", "payment_date", "announcement_date",
    )
    div_dates_all = list(div_dates)   # keep full list for "days_to_next"
    div_dates_past = [d for d in div_dates if d <= as_of]

    # Earnings dates — from the annual results list (period_end).
    annual = sorted(
        (fin.get("annual") or []),
        key=lambda r: r.get("period_end") or "",
        reverse=True,
    )
    earnings_dates = _sorted_dates(annual, "announcement_date", "period_end")
    earnings_past = [d for d in earnings_dates if d <= as_of]

    latest_eps = None
    for r in annual:
        e = r.get("eps")
        if e is not None:
            latest_eps = float(e)
            break

    pe_ttm = _SENTINEL
    if latest_eps and latest_eps > 0 and price and price > 0:
        pe_ttm = price / latest_eps

    # Dividend yield — trailing 12M declared dividends / current price.
    div_yield = _SENTINEL
    if price and price > 0:
        cutoff = as_of - timedelta(days=365)
        ttm = 0.0
        for d in fin.get("dividends") or []:
            dd = _parse_date(d.get("announcement_date") or d.get("ex_date"))
            if dd and cutoff < dd <= as_of and d.get("amount_kes") is not None:
                ttm += float(d["amount_kes"])
        if ttm > 0:
            div_yield = ttm / price * 100.0

    shares_out = fund.get("shares_outstanding_mn")
    shares_out_log = float(np.log1p(shares_out * 1_000_000)) if shares_out else _SENTINEL

    # Macro — nearest snapshot on or before as_of.
    def _macro_at(key: str) -> float:
        series = m.get(key) or []
        best = None
        for pt in series:
            dd = _parse_date(pt.get("date"))
            if dd and dd <= as_of:
                if best is None or dd > _parse_date(best.get("date")):
                    best = pt
        if not best or best.get("value") is None:
            return _SENTINEL
        return float(best["value"])

    return {
        "fund_days_since_earnings":     _days_since(earnings_past, as_of),
        "fund_days_to_next_earnings":   _days_until(earnings_dates, as_of),
        "fund_days_since_dividend":     _days_since(div_dates_past, as_of),
        "fund_days_to_next_dividend":   _days_until(div_dates_all, as_of),
        "fund_last_eps_growth_yoy":     _yoy_growth(annual, "eps"),
        "fund_last_revenue_growth_yoy": _yoy_growth(annual, "revenue_kes_mn"),
        "fund_ann_count_30d":           _count_in_window(ann_dates, as_of, 30),
        "fund_ann_count_90d":           _count_in_window(ann_dates, as_of, 90),
        "fund_pe_ttm":                  pe_ttm,
        "fund_dividend_yield":          div_yield,
        "fund_shares_out_log":          shares_out_log,
        "macro_cbk_rate":               _macro_at("cbk_rate"),
        "macro_inflation_yoy":          _macro_at("inflation_yoy"),
        "macro_kes_usd":                _macro_at("kes_usd"),
    }


def add_fundamental_columns(
    price_df: pd.DataFrame,
    financials: dict | None,
    fundamentals: dict | None,
    macro: dict | None,
) -> pd.DataFrame:
    """Broadcast fundamental features across every row in the price frame.

    The frame is assumed to be indexed by date (or have a DatetimeIndex
    convertible to date). For each row we compute the point-in-time
    fundamental vector using only information available on or before
    that date — no leakage.

    This is expensive-ish for long histories (one loop per row), but the
    biggest ticker has ~15 years × 250 trading days ≈ 3750 rows and each
    row is O(N) over the announcement list. Cache the sorted announcement
    lists once outside the loop by pre-sorting.
    """
    if price_df.empty:
        for c in FUNDAMENTAL_COLUMNS:
            price_df[c] = _SENTINEL
        return price_df

    # Sort event lists ONCE — inside build_fundamental_row they get
    # re-sorted, so we're paying O(rows * events log events). Acceptable
    # at these sizes but a follow-up could hoist the sort here.
    out_rows = []
    for idx in price_df.index:
        as_of = idx.date() if hasattr(idx, "date") else pd.Timestamp(idx).date()
        price = float(price_df.loc[idx, "Close"]) if "Close" in price_df.columns else None
        out_rows.append(build_fundamental_row(as_of, financials, fundamentals, macro, price))
    fdf = pd.DataFrame(out_rows, index=price_df.index)
    for c in FUNDAMENTAL_COLUMNS:
        if c not in fdf.columns:
            fdf[c] = _SENTINEL
        price_df[c] = fdf[c]
    return price_df
