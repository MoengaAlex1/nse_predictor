# pipeline/scripts/deep_price_analysis.py
"""
Combines RTDB price history, technicals, news, corporate actions, and financial
analysis to generate a Claude-powered explanation of recent price movements.

Stores result in Firestore deep_analysis/{ticker}/dates/{YYYY-MM-DD}.

Usage:
  ANTHROPIC_API_KEY=... FIREBASE_SERVICE_ACCOUNT_JSON=... FIREBASE_RTDB_URL=... \\
    python pipeline/scripts/deep_price_analysis.py [--ticker SCOM] [--date 2026-07-24]
"""
import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Ensure repo root on sys.path
_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

SYSTEM_PROMPT = (
    "You are a senior NSE equity analyst. Explain stock price movements using only the "
    "provided data. Be specific about dates, KES figures, and named events. "
    "Do not hallucinate events not present in the input data. "
    "Write in plain English for retail investors."
)

USER_PROMPT_TEMPLATE = """
Analyze the recent price movement for {ticker} on the Nairobi Securities Exchange.

=== RECENT PRICE HISTORY (last 90 days) ===
{price_summary}

=== TECHNICAL SIGNALS (latest) ===
{technicals}

=== RECENT NEWS (last 30 days) ===
{news_items}

=== CORPORATE ACTIONS ===
{corporate_actions}

=== LATEST FINANCIAL ANALYSIS ===
{financial_analysis}

Based ONLY on the above data, respond with a JSON object using exactly these keys:
{{
  "price_movement_explanation": "<2-3 sentences explaining the dominant price driver>",
  "driver_type": "<fundamental|sentiment|technical|corporate_action>",
  "key_events": [
    {{"date": "YYYY-MM-DD", "event": "<description>", "estimated_impact": "<+X% or -X% or neutral>"}}
  ],
  "outlook": {{
    "short_term": "<1-2 sentences, next 2-4 weeks>",
    "medium_term": "<1-2 sentences, next 3-6 months>"
  }},
  "confidence": <integer 1-5>
}}

Return only valid JSON. No markdown fences.
"""


def fetch_price_summary(root_ref, ticker: str, days: int = 90) -> str:
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=days)).isoformat()
    snap = (
        root_ref.child(f"prices/{ticker}")
        .order_by_key()
        .start_at(start_date)
        .end_at(end_date)
        .get()
    )
    if not snap:
        return "No price data available."
    items = sorted(snap.items())
    first, last = items[0], items[-1]
    pct = round(
        ((last[1].get("c", 0) - first[1].get("c", 0)) / (first[1].get("c", 1) or 1)) * 100, 1
    )
    summary = f"90-day change: {pct:+.1f}% (from {first[1].get('c', '?')} to {last[1].get('c', '?')} KES)\n"
    lines = [
        f"{date_str}: open={fields.get('o', '?')} close={fields.get('c', '?')} vol={fields.get('v', '?')}"
        for date_str, fields in items[-10:]
    ]
    return summary + "\n".join(lines)


def fetch_technicals(db, ticker: str) -> str:
    docs = list(
        db.collection("companies")
        .document(ticker)
        .collection("technicals")
        .order_by("__name__", direction="DESCENDING")
        .limit(1)
        .stream()
    )
    if not docs:
        return "No technical data."
    d = docs[0].to_dict()
    wanted = {
        "rsi_14", "macd", "macd_signal", "bb_upper", "bb_lower",
        "sma_20", "sma_50", "sma_200", "volatility_30d",
    }
    return json.dumps({k: v for k, v in d.items() if k in wanted}, indent=2)


def fetch_news(db, ticker: str, days: int = 30) -> str:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    docs = list(db.collection("news").document(ticker).collection("items").stream())
    recent = [d.to_dict() for d in docs if d.to_dict().get("date", "") >= cutoff]
    if not recent:
        return "No recent news."
    return "\n".join(
        f"- [{item['date']}] ({item.get('category', '')}) {item['title']}"
        for item in sorted(recent, key=lambda x: x.get("date", ""), reverse=True)[:15]
    )


def fetch_corporate_actions(db, ticker: str) -> str:
    docs = list(
        db.collection("companies")
        .document(ticker)
        .collection("corporate_actions")
        .order_by("__name__", direction="DESCENDING")
        .limit(10)
        .stream()
    )
    if not docs:
        return "No corporate actions."
    return "\n".join(f"- [{d.id}] {json.dumps(d.to_dict())}" for d in docs)


def fetch_financial_analysis(db, ticker: str) -> str:
    docs = list(
        db.collection("financials")
        .document(ticker)
        .collection("analysis")
        .order_by("__name__", direction="DESCENDING")
        .limit(1)
        .stream()
    )
    if not docs:
        return "No financial analysis available."
    d = docs[0].to_dict()
    return (
        f"Summary: {d.get('summary', '')}\n"
        f"Revenue: {d.get('revenue_trend', '')}\n"
        f"Profit: {d.get('profit_trend', '')}\n"
        f"Risks: {'; '.join(d.get('key_risks', []))}"
    )


def run_analysis(ticker: str, target_date: str, db, root_ref, api_key: str) -> dict:
    short = ticker.replace(".NR", "").replace("_NR", "")

    prompt = USER_PROMPT_TEMPLATE.format(
        ticker=ticker,
        price_summary=fetch_price_summary(root_ref, short),
        technicals=fetch_technicals(db, ticker),
        news_items=fetch_news(db, ticker),
        corporate_actions=fetch_corporate_actions(db, ticker),
        financial_analysis=fetch_financial_analysis(db, ticker),
    )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        log.error("Claude API error for %s: %s", ticker, exc)
        raise
    raw = message.content[0].text.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.error("Non-JSON response for %s: %s", ticker, raw[:200])
        raise ValueError("Claude response was not valid JSON") from exc

    return {
        **result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ticker": ticker,
        "date": target_date,
    }


def save_result(db, ticker: str, date_str: str, result: dict) -> None:
    (
        db.collection("deep_analysis")
        .document(ticker)
        .collection("dates")
        .document(date_str)
        .set(result)
    )
    log.info("Saved deep_analysis/%s/dates/%s", ticker, date_str)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", help="Single ticker (default: all from companies.json)")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.error("ANTHROPIC_API_KEY environment variable is not set.")
        sys.exit(1)

    target_date = args.date or date.today().isoformat()

    from pipeline.scripts.firebase_client import get_firestore, get_rtdb

    db = get_firestore()
    root_ref = get_rtdb()

    if args.ticker:
        tickers = [args.ticker]
    else:
        import json as _json

        config_path = Path(__file__).parent.parent / "config" / "companies.json"
        tickers = [c["ticker"] for c in _json.loads(config_path.read_text())]

    for ticker in tickers:
        try:
            log.info("Analyzing %s ...", ticker)
            result = run_analysis(ticker, target_date, db, root_ref, api_key)
            save_result(db, ticker, target_date, result)
        except Exception as exc:
            log.error("%s: failed — %s", ticker, exc, exc_info=True)


if __name__ == "__main__":
    main()
