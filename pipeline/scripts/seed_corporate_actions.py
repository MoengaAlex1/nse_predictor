"""
Normalise corporate actions already stored in Firestore so price series can be
back-adjusted (phase 0 task 3).

The frontend adjusts splits and bonuses using ratio_new / ratio_old on
financials/{ticker}.corporate_actions. Many records were scraped as free text
("Bonus Issue of 1 for every 5 ordinary shares held") and carry a title but no
typed ratio, so adjustPrices() skips them rather than guessing — which is right,
but it means the adjustment silently does nothing.

This script scans every financials doc, parses ratios out of the titles it can
read, and writes back the typed fields. It never invents an ex-date: if neither
ex_date nor date is present the record is reported and left alone.

Writes to financials/{ticker}.corporate_actions[]:
  type        normalised to one of split | bonus | rights | dividend | other
  ratio_new   int
  ratio_old   int

Usage: python pipeline/scripts/seed_corporate_actions.py [--dry-run]
Env:   FIREBASE_SERVICE_ACCOUNT_JSON
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

# "1 for every 5", "1:5", "one for five", "5 new for 1 old"
_RATIO_PATTERNS = [
    re.compile(r"(\d+)\s*(?:new\s*)?(?:for|:)\s*(?:every\s*)?(\d+)", re.I),
    re.compile(r"ratio\s*of\s*(\d+)\s*(?:to|:)\s*(\d+)", re.I),
]

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_WORD_PATTERN = re.compile(
    r"\b(" + "|".join(_WORDS) + r")\b\s*(?:new\s*)?for\s*(?:every\s*)?\b("
    + "|".join(_WORDS) + r")\b", re.I,
)


def classify(text: str) -> str:
    t = (text or "").lower()
    if "split" in t or "subdivision" in t or "sub-division" in t:
        return "split"
    if "bonus" in t or "capitalisation" in t or "capitalization" in t:
        return "bonus"
    if "rights" in t:
        return "rights"
    if "dividend" in t:
        return "dividend"
    return "other"


def parse_ratio(text: str) -> tuple[int, int] | None:
    """Return (new, old) or None. Never guesses — a miss stays a miss."""
    if not text:
        return None
    for pat in _RATIO_PATTERNS:
        m = pat.search(text)
        if m:
            new, old = int(m.group(1)), int(m.group(2))
            if new > 0 and old > 0:
                return new, old
    m = _WORD_PATTERN.search(text)
    if m:
        return _WORDS[m.group(1).lower()], _WORDS[m.group(2).lower()]
    return None


def action_text(action: dict) -> str:
    return " ".join(str(action.get(k) or "") for k in ("title", "details", "type"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from scripts.firebase_client import get_firestore
    db = get_firestore()

    docs = list(db.collection("financials").stream())
    print(f"Scanning {len(docs)} financials docs for corporate actions")

    typed = skipped_no_ratio = skipped_no_date = touched_docs = 0

    for doc in docs:
        data = doc.to_dict() or {}
        actions = data.get("corporate_actions") or []
        if not actions:
            continue

        changed = False
        for action in actions:
            text = action_text(action)
            kind = classify(text)
            if action.get("type") != kind:
                action["type"] = kind
                changed = True

            if kind not in ("split", "bonus"):
                continue

            if not (action.get("ex_date") or action.get("date")):
                print(f"  {doc.id}: no ex-date for {text[:60]!r} — left alone")
                skipped_no_date += 1
                continue

            if action.get("ratio_new") and action.get("ratio_old"):
                continue

            ratio = parse_ratio(text)
            if ratio is None:
                print(f"  {doc.id}: unparsed ratio in {text[:60]!r}")
                skipped_no_ratio += 1
                continue

            action["ratio_new"], action["ratio_old"] = ratio
            typed += 1
            changed = True
            print(f"  {doc.id}: {kind} {ratio[0]}:{ratio[1]}  ({text[:50]!r})")

        if changed:
            touched_docs += 1
            if not args.dry_run:
                doc.reference.update({"corporate_actions": actions})

    verb = "would type" if args.dry_run else "typed"
    print(
        f"\n{verb} {typed} action(s) across {touched_docs} doc(s); "
        f"{skipped_no_ratio} unparsed ratio(s), {skipped_no_date} without an ex-date"
    )
    if args.dry_run:
        print("dry run — nothing written")


if __name__ == "__main__":
    main()
