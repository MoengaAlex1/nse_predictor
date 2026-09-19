import logging
import numpy as np
from config import ENSEMBLE_WEIGHTS

log = logging.getLogger(__name__)


def ensemble_predict(
    lstm_pred: np.ndarray,
    xgb_pred: np.ndarray,
    arima_pred: np.ndarray,
    weights: tuple = ENSEMBLE_WEIGHTS,
) -> np.ndarray:
    w_lstm, w_xgb, w_arima = weights
    n = min(len(lstm_pred), len(xgb_pred), len(arima_pred))
    return (
        w_lstm  * lstm_pred[:n]  +
        w_xgb   * xgb_pred[:n]  +
        w_arima * arima_pred[:n]
    )


def generate_signal(
    current_price: float,
    predicted_price: float,
    var_pct: float,
    lstm_next: float | None = None,
    xgb_next: float | None = None,
    arima_next: float | None = None,
    technicals: dict | None = None,
    announcements: list[dict] | None = None,
    intraday_features: dict | None = None,
) -> dict:
    from config import NSE_DAILY_BAND_PCT

    pct_change = (predicted_price - current_price) / current_price * 100
    pct_change = max(-NSE_DAILY_BAND_PCT, min(NSE_DAILY_BAND_PCT, pct_change))

    THRESHOLD = 0.5  # ±0.5% minimum predicted change to generate BUY/SELL

    if pct_change > THRESHOLD:
        signal = "BUY"
    elif pct_change < -THRESHOLD:
        signal = "SELL"
    else:
        signal = "HOLD"

    # Risk-adjusted signal: predicted gain must cover at least 25% of 95% VaR
    risk_signal = signal if (signal == "HOLD" or abs(pct_change) >= 0.25 * abs(var_pct)) else "HOLD"

    # ── Per-model votes ───────────────────────────────────────────────────────
    _model_inputs: list[tuple[str, float | None]] = [
        ("LSTM",    lstm_next),
        ("XGBoost", xgb_next),
        ("ARIMA",   arima_next),
    ]
    model_breakdown: dict[str, dict] = {}
    for name, price in _model_inputs:
        if price is None:
            continue
        m_pct = round((price - current_price) / current_price * 100, 2)
        if m_pct > THRESHOLD:
            m_sig = "BUY"
        elif m_pct < -THRESHOLD:
            m_sig = "SELL"
        else:
            m_sig = "HOLD"
        model_breakdown[name] = {"price": round(price, 2), "pct": m_pct, "signal": m_sig}

    n_models = len(model_breakdown)
    agreeing = sum(1 for m in model_breakdown.values() if m["signal"] == signal)
    model_agreement = round(agreeing / n_models * 100) if n_models > 0 else 50

    # ── Technical indicator support ───────────────────────────────────────────
    t = technicals or {}
    rsi       = t.get("rsi_14")
    macd_hist = t.get("macd_hist")
    sma_20    = t.get("sma_20")
    bb_upper  = t.get("bb_upper")
    bb_lower  = t.get("bb_lower")

    rsi_supports = (
        (signal == "BUY"  and rsi is not None and rsi < 40) or
        (signal == "SELL" and rsi is not None and rsi > 60)
    )
    macd_supports = (
        (signal == "BUY"  and macd_hist is not None and macd_hist > 0) or
        (signal == "SELL" and macd_hist is not None and macd_hist < 0)
    )
    sma_supports = (
        (signal == "BUY"  and sma_20 is not None and current_price < sma_20) or
        (signal == "SELL" and sma_20 is not None and current_price > sma_20)
    )
    bb_supports = (
        (signal == "BUY"  and bb_lower is not None and current_price <= bb_lower * 1.02) or
        (signal == "SELL" and bb_upper is not None and current_price >= bb_upper * 0.98)
    )

    # ── Confidence score (20-95) ──────────────────────────────────────────────
    confidence = 50
    if signal != "HOLD":
        if n_models == 3 and agreeing == 3:
            confidence += 25
        elif agreeing >= 2:
            confidence += 15
        else:
            confidence -= 10
        if rsi_supports:       confidence += 10
        if macd_supports:      confidence += 5
        if sma_supports:       confidence += 5
        if bb_supports:        confidence += 5
        if risk_signal == "HOLD":
            confidence -= 15
    confidence = max(20, min(95, confidence))

    # ── Reasons list ──────────────────────────────────────────────────────────
    reasons: list[str] = []
    pct_abs = abs(pct_change)

    if signal == "BUY":
        reasons.append(
            f"Ensemble model predicts a +{pct_abs:.2f}% price increase "
            f"to KES {predicted_price:.2f}"
        )
    elif signal == "SELL":
        reasons.append(
            f"Ensemble model predicts a {pct_change:.2f}% price decline "
            f"to KES {predicted_price:.2f}"
        )
    else:
        reasons.append(
            f"Predicted change of {pct_change:+.2f}% is within the ±{THRESHOLD}% "
            f"noise threshold — no clear direction"
        )

    if n_models > 0:
        names_list = ", ".join(model_breakdown.keys())
        if agreeing == n_models and n_models > 1:
            reasons.append(
                f"All {n_models} models ({names_list}) agree on the {signal} "
                f"direction — strong consensus"
            )
        elif agreeing >= 2:
            agree_names = ", ".join(m for m, v in model_breakdown.items() if v["signal"] == signal)
            reasons.append(
                f"{agreeing}/{n_models} models agree ({agree_names}) — moderate consensus"
            )
        elif agreeing == 1:
            reasons.append(
                f"Only 1/{n_models} models agrees on {signal}; the others diverge — treat with caution"
            )

    if rsi is not None:
        if signal == "BUY" and rsi < 40:
            reasons.append(
                f"RSI at {rsi:.0f} signals the stock is oversold (below 40), "
                f"suggesting potential recovery"
            )
        elif signal == "SELL" and rsi > 60:
            reasons.append(
                f"RSI at {rsi:.0f} signals the stock is overbought (above 60), "
                f"suggesting a potential pullback"
            )
        elif rsi < 30:
            reasons.append(
                f"RSI at {rsi:.0f} is strongly oversold — models don't yet confirm recovery"
            )
        elif rsi > 70:
            reasons.append(
                f"RSI at {rsi:.0f} is strongly overbought — models don't yet confirm a decline"
            )

    if macd_hist is not None and macd_supports:
        direction_word = "bullish" if signal == "BUY" else "bearish"
        reasons.append(
            f"MACD histogram is {'positive' if macd_hist > 0 else 'negative'} "
            f"({macd_hist:+.4f}) — {direction_word} momentum supports the {signal} signal"
        )

    if sma_20 is not None:
        if signal == "BUY" and current_price < sma_20:
            reasons.append(
                f"Price (KES {current_price:.2f}) is below the 20-day moving average "
                f"(KES {sma_20:.2f}) — a recovery above SMA20 could trigger further buying"
            )
        elif signal == "SELL" and current_price > sma_20:
            reasons.append(
                f"Price (KES {current_price:.2f}) is above the 20-day moving average "
                f"(KES {sma_20:.2f}) — a break below SMA20 may accelerate selling"
            )

    if bb_lower is not None and bb_upper is not None:
        if signal == "BUY" and current_price <= bb_lower * 1.02:
            reasons.append(
                f"Price is near the lower Bollinger Band (KES {bb_lower:.2f}) "
                f"— historically a mean-reversion buy zone"
            )
        elif signal == "SELL" and current_price >= bb_upper * 0.98:
            reasons.append(
                f"Price is near the upper Bollinger Band (KES {bb_upper:.2f}) "
                f"— historically a mean-reversion sell zone"
            )

    # ── Expanded indicator evidence (2026-09-19) ───────────────────────────
    # Only include lines that actually MATCH the direction we're signalling
    # so the reasons list stays focused on supporting evidence rather than
    # dumping every field.
    adx     = t.get("adx_14")
    stoch_k = t.get("stoch_k")
    vwap    = t.get("vwap_14")
    cci     = t.get("cci_20")

    if adx is not None:
        if adx >= 25 and signal != "HOLD":
            reasons.append(
                f"ADX at {adx:.0f} indicates a strong trend — the {signal} signal "
                f"is unfolding in a trending market (>25 threshold)"
            )
        elif adx < 20 and signal == "HOLD":
            reasons.append(
                f"ADX at {adx:.0f} confirms a ranging (non-trending) market — "
                f"consistent with the HOLD signal; wait for a breakout"
            )

    if stoch_k is not None:
        if signal == "BUY" and stoch_k < 20:
            reasons.append(
                f"Stochastic %K at {stoch_k:.0f} is oversold (<20) — reinforces buy timing"
            )
        elif signal == "SELL" and stoch_k > 80:
            reasons.append(
                f"Stochastic %K at {stoch_k:.0f} is overbought (>80) — reinforces sell timing"
            )

    if vwap is not None and vwap > 0:
        vwap_delta = (current_price - vwap) / vwap * 100
        if signal == "BUY" and vwap_delta < -1:
            reasons.append(
                f"Price (KES {current_price:.2f}) is {abs(vwap_delta):.1f}% below "
                f"14-day VWAP (KES {vwap:.2f}) — trading at a volume-weighted discount"
            )
        elif signal == "SELL" and vwap_delta > 1:
            reasons.append(
                f"Price (KES {current_price:.2f}) is {vwap_delta:.1f}% above "
                f"14-day VWAP (KES {vwap:.2f}) — trading at a volume-weighted premium"
            )

    if cci is not None:
        if signal == "BUY" and cci < -100:
            reasons.append(
                f"CCI at {cci:.0f} is oversold (<-100) — mean-reversion setup supports the BUY"
            )
        elif signal == "SELL" and cci > 100:
            reasons.append(
                f"CCI at {cci:.0f} is overbought (>+100) — mean-reversion setup supports the SELL"
            )

    # ── Intraday alignment ─────────────────────────────────────────────────
    # Intraday features are today-only (see push_intraday_prices.py). When
    # they exist and point the same direction as the daily model, that's
    # meaningful corroboration; when they contradict, we call it out so
    # users know the daily signal might reverse before EOD.
    if intraday_features:
        drift = intraday_features.get("intra_opening_drift_pct")
        last_hour = intraday_features.get("intra_last_hour_momentum_pct")
        bias = intraday_features.get("intra_direction_bias")
        vs_prev = intraday_features.get("intra_vs_prev_close_pct")
        n_snaps = intraday_features.get("intra_snapshots") or 0

        if n_snaps >= 3:
            # Direction consistency: does the intraday tape confirm the
            # signal or push against it?
            def _same_dir(v):
                if v is None: return None
                if signal == "BUY"  and v > 0.1: return True
                if signal == "SELL" and v < -0.1: return True
                if signal in ("BUY", "SELL") and abs(v) <= 0.1: return None
                if signal == "BUY"  and v < -0.1: return False
                if signal == "SELL" and v > 0.1: return False
                return None

            confirm_bits: list[str] = []
            contradict_bits: list[str] = []
            for label, v in [("opening drift", drift), ("last-hour move", last_hour)]:
                s = _same_dir(v)
                if s is True and v is not None:
                    confirm_bits.append(f"{label} {v:+.2f}%")
                elif s is False and v is not None:
                    contradict_bits.append(f"{label} {v:+.2f}%")

            if confirm_bits:
                reasons.append(
                    f"Intraday tape confirms {signal}: "
                    + "; ".join(confirm_bits)
                    + f" (over {int(n_snaps)} snapshots today)"
                )
            elif contradict_bits and signal != "HOLD":
                reasons.append(
                    f"⚠ Intraday tape is pushing against the {signal}: "
                    + "; ".join(contradict_bits)
                    + " — the signal may reverse before close; consider waiting"
                )

            if bias is not None and abs(bias) >= 0.4:
                bias_word = "buyers" if bias > 0 else "sellers"
                reasons.append(
                    f"Direction bias {bias:+.2f} — {bias_word} control "
                    f"the intraday tape ({int(n_snaps)} snapshots)"
                )

            if vs_prev is not None and abs(vs_prev) >= 3.0 and signal == "HOLD":
                reasons.append(
                    f"Live price is {vs_prev:+.2f}% vs previous close but "
                    f"the daily models still call HOLD — likely mean-reversion "
                    f"before EOD"
                )

    # ── Announcement / filings context ──────────────────────────────────────
    # Count filings in the last 30 days by kind; surface any concentration
    # that could plausibly influence the near-term price. This is descriptive
    # only — we don't try to score sentiment.
    if announcements:
        from datetime import date as _date, timedelta as _td
        cutoff = (_date.today() - _td(days=30)).isoformat()
        recent = [a for a in announcements
                  if isinstance(a, dict) and str(a.get("date", "")) >= cutoff]
        by_kind: dict[str, int] = {}
        for a in recent:
            k = str(a.get("type") or a.get("category") or "other").lower()
            by_kind[k] = by_kind.get(k, 0) + 1
        top = [(k, n) for k, n in by_kind.items() if n >= 2]
        if len(recent) >= 3:
            summary = ", ".join(f"{n} {k}" for k, n in sorted(top, key=lambda kv: -kv[1])[:3])
            reasons.append(
                f"{len(recent)} filings in the last 30 days"
                + (f" ({summary})" if summary else "")
                + " — elevated corporate-action context; check the Filings tab"
            )

    if risk_signal == "HOLD" and signal != "HOLD":
        reasons.append(
            f"⚠ Risk note: predicted move ({pct_abs:.2f}%) is small relative to "
            f"the 95% Value at Risk ({abs(var_pct):.2f}%) — risk-adjusted signal is HOLD"
        )

    # ── Implications paragraph ────────────────────────────────────────────────
    var_str = f"{abs(var_pct):.1f}%"
    agree_str = f"{agreeing}/{n_models}" if n_models > 0 else "multiple"

    if signal == "BUY":
        implications = (
            f"Our models suggest this stock may rise from KES {current_price:.2f} "
            f"to KES {predicted_price:.2f} (+{pct_abs:.2f}%) by the next trading session. "
            f"The BUY signal is supported by {agree_str} prediction models. "
            f"The 95% Value at Risk is {var_str}, meaning in a bad scenario "
            f"you could lose more than {var_str} of your investment. "
            + (
                "The risk-adjusted signal also confirms BUY."
                if risk_signal == "BUY" else
                "However, the risk-adjusted signal is HOLD due to the predicted gain "
                "being small relative to market volatility — consider a smaller position size."
            )
        )
    elif signal == "SELL":
        implications = (
            f"Our models suggest this stock may fall from KES {current_price:.2f} "
            f"to KES {predicted_price:.2f} ({pct_change:.2f}%) by the next trading session. "
            f"If you hold shares, consider reducing your position. "
            f"The SELL signal is supported by {agree_str} prediction models. "
            f"The 95% Value at Risk is {var_str}. "
            + (
                "The risk-adjusted signal confirms SELL."
                if risk_signal == "SELL" else
                "The risk-adjusted signal is HOLD — this is a cautionary signal, not a certain decline."
            )
        )
    else:
        implications = (
            f"The models predict a minimal price change of {pct_change:+.2f}% "
            f"(from KES {current_price:.2f} to KES {predicted_price:.2f}). "
            f"This is within normal market noise and does not present a clear trading opportunity. "
            f"Monitor this stock over the next few sessions for a stronger directional signal. "
            f"The 95% Value at Risk is {var_str}."
        )

    rationale = reasons[0] if reasons else f"Model predicts {pct_change:+.2f}%"

    return {
        "signal":               signal,
        "risk_adjusted_signal": risk_signal,
        "current_price_KES":    round(current_price, 2),
        "predicted_price_KES":  round(predicted_price, 2),
        "predicted_change_pct": round(pct_change, 2),
        "var_95_pct":           round(var_pct, 2),
        "rationale":            rationale,
        "signal_reasons":       reasons,
        "signal_implications":  implications,
        "confidence_score":     confidence,
        "model_agreement":      model_agreement,
        "model_breakdown":      model_breakdown,
    }


def compute_ensemble_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae  = float(mean_absolute_error(y_true, y_pred))
    mape = float(np.mean(np.abs((y_true - y_pred) / np.where(y_true == 0, 1, y_true))) * 100)
    dir_acc = float(np.mean(np.sign(np.diff(y_true)) == np.sign(np.diff(y_pred))) * 100)
    log.info("[Ensemble] RMSE: %.4f | MAE: %.4f | MAPE: %.2f%% | Dir Acc: %.1f%%", rmse, mae, mape, dir_acc)
    return {"rmse": rmse, "mae": mae, "mape": mape, "directional_accuracy": dir_acc}
