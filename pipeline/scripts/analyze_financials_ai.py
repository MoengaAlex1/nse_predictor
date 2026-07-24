# pipeline/scripts/analyze_financials_ai.py
"""
Reads extracted financials from Firestore and generates investor narrative via Claude API.
Stores result in Firestore financials/{ticker}/analysis/{period}.

Usage:
  ANTHROPIC_API_KEY=... FIREBASE_SERVICE_ACCOUNT_JSON=... \\
    python pipeline/scripts/analyze_financials_ai.py --ticker BAT --period H1-2026
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Ensure repo root on sys.path
_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

SYSTEM_PROMPT = (
    "You are a senior Kenyan equity analyst writing concise, plain-English investor commentary "
    "for retail investors on the Nairobi Securities Exchange. "
    "Be factual, specific about KES figures, and highlight risks honestly. "
    "Avoid jargon. Write in present tense."
)

USER_PROMPT_TEMPLATE = """
Given these financial results for {ticker} ({period} vs {comparison}):

{financials_json}

Write a structured analysis as JSON with exactly these keys:
{{
  "summary": "<3 sentences covering overall performance>",
  "revenue_trend": "<direction and main driver>",
  "profit_trend": "<margins and trajectory>",
  "debt_levels": "<risk assessment based on retained earnings and shareholders funds>",
  "cash_flow_health": "<sustainability based on operating and investing cash flows>",
  "dividend_history": "<dividend coverage and sustainability given EPS and DPS>",
  "key_risks": ["<risk 1>", "<risk 2>", "<risk 3>"],
  "growth_opportunities": ["<opportunity 1>", "<opportunity 2>"]
}}

Return only valid JSON. No markdown fences. No extra keys.
"""


def build_prompt(ticker: str, period: str, comparison: str, financials: dict) -> str:
    return USER_PROMPT_TEMPLATE.format(
        ticker=ticker,
        period=period,
        comparison=comparison,
        financials_json=json.dumps(financials, indent=2),
    )


def call_claude(prompt: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
    )
    raw = message.content[0].text.strip()
    return json.loads(raw)


def save_analysis(db, ticker: str, period: str, analysis: dict) -> None:
    analysis["generated_at"] = datetime.now(timezone.utc).isoformat()
    (db.collection("financials")
       .document(ticker)
       .collection("analysis")
       .document(period)
       .set(analysis))
    log.info("Saved analysis for %s / %s", ticker, period)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--period", required=True, help="e.g. H1-2026")
    args = parser.parse_args()

    from pipeline.scripts.firebase_client import get_firestore
    db = get_firestore()

    doc = (db.collection("financials")
             .document(args.ticker)
             .collection("periods")
             .document(args.period)
             .get())
    if not doc.exists:
        log.error("No extracted metrics for %s / %s. Run extract_financials first.", args.ticker, args.period)
        return

    data = doc.to_dict()
    comparison = data.get("comparison_period", "prior period")
    prompt = build_prompt(args.ticker, args.period, comparison, data)

    log.info("Calling Claude API for %s / %s ...", args.ticker, args.period)
    analysis = call_claude(prompt)
    save_analysis(db, args.ticker, args.period, analysis)
    log.info("Done.")


if __name__ == "__main__":
    main()
