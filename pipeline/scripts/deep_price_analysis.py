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
from typing import Any

import anthropic

# Ensure repo root on sys.path before importing sibling packages
_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from pipeline.scripts.firebase_client import get_firestore, get_rtdb  # noqa: E402

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

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


def fetch_price_summary(root_ref: Any, ticker: str, days: int = 90) -> list[dict]:
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
        return []
    return [
        {"date": date_str, **fields}
        for date_str, fields in sorted(snap.items())
    ]


def fetch_technicals(db: Any, ticker: str) -> dict:
    docs = list(
        db.collection("companies")
        .document(ticker)
        .collection("technicals")
        .order_by("__name__", direction="DESCENDING")
        .limit(1)
        .stream()
    )
    if not docs:
        return {}
    d = docs[0].to_dict()
    wanted = {
        "rsi_14", "macd", "macd_signal", "bb_upper", "bb_lower",
        "sma_20", "sma_50", "sma_200", "volatility_30d",
    }
    return {k: v for k, v in d.items() if k in wanted}


def fetch_news(db: Any, ticker: str, days: int = 30) -> list[dict]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    docs = list(db.collection("news").document(ticker).collection("items").stream())
    all_dicts = [d.to_dict() for d in docs]
    recent = [d for d in all_dicts if d.get("date", "") >= cutoff]
    return sorted(recent, key=lambda x: x.get("date", ""), reverse=True)[:15]


def fetch_corporate_actions(db: Any, ticker: str) -> dict:
    docs = list(
        db.collection("companies")
        .document(ticker)
        .collection("corporate_actions")
        .order_by("__name__", direction="DESCENDING")
        .limit(10)
        .stream()
    )
    if not docs:
        return {}
    return {d.id: d.to_dict() for d in docs}


def fetch_financial_analysis(db: Any, ticker: str) -> dict:
    docs = list(
        db.collection("financials")
        .document(ticker)
        .collection("analysis")
        .order_by("__name__", direction="DESCENDING")
        .limit(1)
        .stream()
    )
    if not docs:
        return {}
    return docs[0].to_dict()


def run_analysis(ticker: str, target_date: str, db: Any, root_ref: Any, api_key: str) -> dict:
    short = ticker.replace(".NR", "").replace("_NR", "")

    price_data = fetch_price_summary(root_ref, short)
    technicals_data = fetch_technicals(db, ticker)
    news_data = fetch_news(db, ticker)
    corporate_actions_data = fetch_corporate_actions(db, ticker)
    financial_analysis_data = fetch_financial_analysis(db, ticker)

    prompt = USER_PROMPT_TEMPLATE.format(
        ticker=ticker,
        price_summary=json.dumps(price_data, indent=2) if price_data else "No price data available.",
        technicals=json.dumps(technicals_data, indent=2) if technicals_data else "No technical data.",
        news_items=json.dumps(news_data, indent=2) if news_data else "No recent news.",
        corporate_actions=json.dumps(corporate_actions_data, indent=2) if corporate_actions_data else "No corporate actions.",
        financial_analysis=json.dumps(financial_analysis_data, indent=2) if financial_analysis_data else "No financial analysis available.",
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
    if not message.content:
        raise ValueError("Claude returned an empty content list")
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


def save_result(db: Any, ticker: str, date_str: str, result: dict) -> None:
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

    firebase_sa = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not firebase_sa:
        log.error("FIREBASE_SERVICE_ACCOUNT_JSON environment variable is not set.")
        sys.exit(1)

    rtdb_url = os.environ.get("FIREBASE_RTDB_URL")
    if not rtdb_url:
        log.error("FIREBASE_RTDB_URL environment variable is not set.")
        sys.exit(1)

    target_date = args.date or date.today().isoformat()

    db = get_firestore()
    root_ref = get_rtdb()

    if args.ticker:
        tickers = [args.ticker]
    else:
        config_path = Path(__file__).parent.parent / "config" / "companies.json"
        tickers = [c["ticker"] for c in json.loads(config_path.read_text())]

    for ticker in tickers:
        try:
            log.info("Analyzing %s ...", ticker)
            result = run_analysis(ticker, target_date, db, root_ref, api_key)
            save_result(db, ticker, target_date, result)
        except Exception as exc:
            log.error("%s: failed — %s", ticker, exc, exc_info=True)


if __name__ == "__main__":
    main()
