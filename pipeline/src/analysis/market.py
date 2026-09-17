# pipeline/src/analysis/market.py
"""Shared market-overview aggregation used by inference and daily-update."""

import logging

# Relative import so the module works both when the pipeline runs with
# `pipeline/` on sys.path (production, `from src.analysis... import ...`)
# and when the test suite imports `pipeline.src.analysis.market` directly.
from .indices import fetch_market_indices

log = logging.getLogger(__name__)


def aggregate_market_overview(
    results: list[dict],
    date_str: str,
    indices: dict[str, dict] | None = None,
) -> dict:
    """Aggregate per-company inference results into a market-level summary.

    Parameters
    ----------
    results:
        List of dicts returned by each company's run_company(). Each entry
        has "ticker", "public_update" (current_price, change_pct_today,
        signal), and "technicals" (with .volume field). None entries are
        skipped.
    date_str:
        ISO date string for the 'date' field.

    Adds most_active — top 5 tickers by day's traded volume, with turnover
    computed as volume × current_price. Home page's "Most Active" box reads
    from this field.

    indices:
        Optional. Live NSE market-statistics readings keyed by canonical
        short (NASI, NSE20, NSE25, NSE10, NSEBSI, MCAP, ...). When None,
        this function calls fetch_market_indices() itself; when an empty
        dict is passed the indices field is written as {} (used by tests
        so we don't hit the live NSE site). Home page's Market Heatmap
        reads market.indices.
    """
    rows: list[tuple[str, float]] = []
    volume_rows: list[tuple[str, int, float, float]] = []  # (tkr, volume, price, change_pct)
    signals: dict[str, int] = {"BUY": 0, "HOLD": 0, "SELL": 0}

    for r in results:
        if r is None:
            continue
        pub = r["public_update"]
        tkr = r["ticker"]
        change_pct = pub["change_pct_today"]
        rows.append((tkr, change_pct))
        sig = pub["signal"]
        signals[sig] = signals.get(sig, 0) + 1

        tech = r.get("technicals") or {}
        vol = tech.get("volume")
        price = pub.get("current_price") or 0
        if isinstance(vol, (int, float)) and vol > 0:
            volume_rows.append((tkr, int(vol), float(price), change_pct))

    rows.sort(key=lambda x: x[1], reverse=True)
    top_gainers = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[:5]]
    top_losers  = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[-5:]]

    # Most active by volume — the actual industry-standard "most active"
    # metric. Turnover (KES) provided too for reference / sort variants.
    volume_rows.sort(key=lambda x: x[1], reverse=True)
    most_active = [
        {
            "ticker":       t,
            "volume":       v,
            "turnover_kes": round(v * p, 2),
            "change_pct":   round(cp, 2),
        }
        for t, v, p, cp in volume_rows[:5]
    ]

    # Fetch live indices unless caller pre-supplied them (tests pass {} to
    # avoid the network call). None → do the fetch; {} → treat as "nothing
    # available today" and skip.
    if indices is None:
        indices = fetch_market_indices() or {}

    nse20 = indices.get("NSE20") or {}

    return {
        "date":                date_str,
        "top_gainers":         top_gainers,
        "top_losers":          top_losers,
        "most_active":         most_active,
        "signal_distribution": signals,
        "sector_performance":  {},
        # Full six-index panel (NASI, NSE 20, NSE 25, NSE 10, NSE BSI, M.CAP)
        # plus turnover/volume/deals if the NSE feed included them. Consumed
        # by frontend MarketHeatmap. Empty dict means the feed was unreachable
        # at write-time — the UI shows nothing rather than fabricating values.
        "indices":             indices,
        # Legacy fields, kept for existing TickerTape / MarketSummaryStrip
        # readers. Populated from indices.NSE20 when present so we never
        # again ship a doc with NSE20 unset but indices carrying it.
        "nse20_value":         nse20.get("value"),
        "nse20_change_pct":    nse20.get("change_pct"),
    }
