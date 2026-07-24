"""
Extracts financial metrics from NSE company half-year and annual report PDFs.
All 20 mandated fields are extracted. Unextractable fields are stored as null.

Usage:
  python pipeline/scripts/extract_financials.py --pdf path/to/report.pdf \
    --ticker BAT --period H1-2026 --comparison H1-2025
"""
import argparse
import json
import logging
import re
import sys
from pathlib import Path

import pdfplumber

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Ensure repo root on sys.path for sibling package imports
_REPO_ROOT = str(Path(__file__).parent.parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def clean_value(raw: str) -> float | None:
    """Parse a financial value string to float. Parentheses = negative. Returns None if unparseable."""
    if not raw:
        return None
    s = str(raw).strip()
    if s in ("-", "—", "n/a", "N/A", "nil", ""):
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[(),]", "", s)
    s = re.sub(r"[Bb][Nn]$", "", s)
    s = re.sub(r"[Mm][Nn]$", "", s)
    s = re.sub(r"[,\s]", "", s)
    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


def parse_unit(raw: str) -> str:
    s = str(raw).upper()
    if "BN" in s:
        return "Bn"
    if "MN" in s or "MILLION" in s:
        return "Mn"
    return "KES"


def build_metric(current, prior, unit: str = "KES", currency: str = "KES") -> dict:
    yoy = None
    if current is not None and prior is not None and prior != 0:
        yoy = round(((current - prior) / abs(prior)) * 100, 2)
    return {
        "current":  current,
        "prior":    prior,
        "yoy_pct":  yoy,
        "unit":     unit,
        "currency": currency,
    }


def EMPTY_FINANCIALS() -> dict:
    """Return a template with all required keys set to null metrics."""
    null_m = {"current": None, "prior": None, "yoy_pct": None, "unit": "KES", "currency": "KES"}
    null_roe = {"current": None, "prior": None, "direction": None}
    return {
        "income_statement": {
            "gross_revenue":       dict(null_m),
            "excise_duty_and_vat": dict(null_m),
            "net_revenue":         dict(null_m),
            "cost_of_operations":  dict(null_m),
            "operating_profit":    dict(null_m),
            "finance_income":      dict(null_m),
            "profit_before_tax":   dict(null_m),
            "income_tax_expense":  dict(null_m),
            "profit_after_tax":    dict(null_m),
        },
        "per_share": {
            "basic_diluted_eps":          dict(null_m),
            "interim_dividend_per_share": dict(null_m),
        },
        "balance_sheet": {
            "retained_earnings":  dict(null_m),
            "shareholders_funds": dict(null_m),
        },
        "cash_flow": {
            "net_cash_from_operations":       dict(null_m),
            "net_cash_operating_activities":  dict(null_m),
            "net_cash_investing_activities":  dict(null_m),
            "net_cash_financing_activities":  dict(null_m),
            "movement_in_cash":               dict(null_m),
            "cash_at_period_end":             dict(null_m),
        },
        "returns": {
            "annualised_roe": dict(null_roe),
        },
    }


# Keyword patterns for matching PDF table rows to metric keys
METRIC_KEYWORDS: dict[str, list[str]] = {
    "gross_revenue":                  ["gross revenue", "gross turnover"],
    "excise_duty_and_vat":            ["excise", "vat"],
    "net_revenue":                    ["net revenue", "net turnover", "revenue after excise"],
    "cost_of_operations":             ["cost of operations", "cost of sales", "operating costs"],
    "operating_profit":               ["operating profit", "profit from operations"],
    "finance_income":                 ["finance income", "interest income", "investment income"],
    "profit_before_tax":              ["profit before tax", "pbt"],
    "income_tax_expense":             ["income tax", "tax expense", "taxation"],
    "profit_after_tax":               ["profit after tax", "pat", "profit for the period"],
    "basic_diluted_eps":              ["earnings per share", "eps", "basic"],
    "interim_dividend_per_share":     ["dividend per share", "dps", "interim dividend"],
    "retained_earnings":              ["retained earnings", "retained profit"],
    "shareholders_funds":             ["shareholders' funds", "shareholders funds", "total equity"],
    "net_cash_from_operations":       ["cash generated from operations", "cash from operations"],
    "net_cash_operating_activities":  ["net cash from operating", "operating activities"],
    "net_cash_investing_activities":  ["investing activities", "net cash used in investing"],
    "net_cash_financing_activities":  ["financing activities", "net cash used in financing"],
    "movement_in_cash":               ["movement in cash", "net movement", "increase in cash"],
    "cash_at_period_end":             ["cash at end", "cash and cash equivalents at end", "closing cash"],
    "annualised_roe":                 ["annualised roe", "return on equity", "roe"],
}


def match_metric(label: str) -> str | None:
    lower = label.lower().strip()
    for key, patterns in METRIC_KEYWORDS.items():
        if any(p in lower for p in patterns):
            return key
    return None


def extract_from_pdf(pdf_path: str) -> dict:
    """Parse PDF tables and return populated financials dict."""
    result = EMPTY_FINANCIALS()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in table:
                    if not row or len(row) < 2:
                        continue
                    label = str(row[0] or "").strip()
                    metric_key = match_metric(label)
                    if not metric_key:
                        continue

                    numbers = [clean_value(str(c)) for c in row[1:] if c is not None]
                    numbers = [n for n in numbers if n is not None]

                    unit = parse_unit(label + " ".join(str(c) for c in row))
                    currency = "KES"

                    if metric_key == "annualised_roe":
                        cur_raw = str(row[1] or "").strip() if len(row) > 1 else ""
                        pri_raw = str(row[2] or "").strip() if len(row) > 2 else ""
                        cur_pct = cur_raw if "%" in cur_raw else (f"{numbers[0]}%" if numbers else None)
                        pri_pct = pri_raw if "%" in pri_raw else (f"{numbers[1]}%" if len(numbers) > 1 else None)
                        direction = (
                            "increased" if numbers and len(numbers) > 1 and numbers[0] > numbers[1]
                            else "decreased" if numbers and len(numbers) > 1 and numbers[0] < numbers[1]
                            else None
                        )
                        result["returns"]["annualised_roe"] = {
                            "current":   cur_pct,
                            "prior":     pri_pct,
                            "direction": direction,
                        }
                        continue

                    current = numbers[0] if numbers else None
                    prior   = numbers[1] if len(numbers) > 1 else None
                    metric  = build_metric(current, prior, unit=unit, currency=currency)

                    for section in ("income_statement", "per_share", "balance_sheet", "cash_flow"):
                        if metric_key in result[section]:
                            result[section][metric_key] = metric
                            break
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf",        required=True)
    parser.add_argument("--ticker",     required=True)
    parser.add_argument("--period",     required=True, help="e.g. H1-2026")
    parser.add_argument("--comparison", required=True, help="e.g. H1-2025")
    parser.add_argument("--out",        help="Output JSON path")
    args = parser.parse_args()

    data = extract_from_pdf(args.pdf)
    data["ticker"]            = args.ticker
    data["period"]            = args.period
    data["comparison_period"] = args.comparison

    out = args.out or f"{args.ticker}_{args.period}_financials.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    log.info("Saved to %s", out)


if __name__ == "__main__":
    main()
