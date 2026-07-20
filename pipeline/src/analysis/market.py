# pipeline/src/analysis/market.py
"""Shared market-overview aggregation used by inference and daily-update."""


def aggregate_market_overview(results: list[dict], date_str: str) -> dict:
    """Aggregate per-company inference results into a market-level summary.

    Parameters
    ----------
    results:
        List of dicts returned by each company's run_company(). None entries are skipped.
    date_str:
        ISO date string for the 'date' field.
    """
    rows: list[tuple[str, float]] = []
    signals: dict[str, int] = {"BUY": 0, "HOLD": 0, "SELL": 0}

    for r in results:
        if r is None:
            continue
        pub = r["public_update"]
        rows.append((r["ticker"], pub["change_pct_today"]))
        sig = pub["signal"]
        signals[sig] = signals.get(sig, 0) + 1

    rows.sort(key=lambda x: x[1], reverse=True)
    top_gainers = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[:5]]
    top_losers  = [{"ticker": t, "change_pct": round(c, 2)} for t, c in rows[-5:]]

    return {
        "date":                date_str,
        "top_gainers":         top_gainers,
        "top_losers":          top_losers,
        "signal_distribution": signals,
        "sector_performance":  {},
        "nse20_value":         None,
        "nse20_change_pct":    None,
    }
