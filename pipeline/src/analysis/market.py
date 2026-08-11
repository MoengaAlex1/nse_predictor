# pipeline/src/analysis/market.py
"""Shared market-overview aggregation used by inference and daily-update."""


def aggregate_market_overview(results: list[dict], date_str: str) -> dict:
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

    return {
        "date":                date_str,
        "top_gainers":         top_gainers,
        "top_losers":          top_losers,
        "most_active":         most_active,
        "signal_distribution": signals,
        "sector_performance":  {},
        "nse20_value":         None,
        "nse20_change_pct":    None,
    }
