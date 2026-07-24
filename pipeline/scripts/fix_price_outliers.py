"""
fix_price_outliers.py

Cleans price_history in Firestore companies/{ticker} documents by detecting
and removing price spikes caused by missing decimal errors (e.g. 90.00 instead
of 9.00).

Detection: global-median approach — compute the median of ALL price points in
the full history, then remove any point whose price is more than OUTLIER_HIGH_X
times or less than OUTLIER_LOW_X times the global median. This handles
clustered multi-week spikes (where a local rolling-median would fail because
the bad points anchor each other's median value).

Usage:
    firebase projects:list          # refresh OAuth token first
    python pipeline/scripts/fix_price_outliers.py [--dry-run] [--ticker BRIT_NR]

Token source (checked in order):
    1. FIREBASE_TOKEN environment variable
    2. Access token in ~/.config/configstore/firebase-tools.json
    3. Auto-refresh using stored refresh_token + GOOGLE_CLIENT_ID/SECRET
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests

PIPELINE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PIPELINE_ROOT.parent))
sys.path.insert(0, str(PIPELINE_ROOT))

from config import load_companies

PROJECT_ID = "nse-market-dashboard"
FIRESTORE_BASE = (
    f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
    "/databases/(default)/documents"
)

# Within any given calendar year, a legitimate price should not deviate more
# than YEAR_RATIO from the median of that year. Missing-decimal errors (10x off)
# are always caught; genuine historical bull/bear swings within a year stay.
YEAR_RATIO = 6.0

# Pre-screen factor: exclude points > this many × global median before computing
# year medians. Ensures a poisoned year (where bad data is the majority of that
# year's points) still gets a correct reference median from the clean minority.
# 20x is wide enough to not touch any legitimate multi-year price swings.
GLOBAL_PRESCREEN_FACTOR = 20.0


# ── Token helpers ──────────────────────────────────────────────────────────────

def _load_firebase_config() -> dict:
    fb_tools = Path.home() / ".config" / "configstore" / "firebase-tools.json"
    if not fb_tools.exists():
        return {}
    return json.loads(fb_tools.read_text(encoding="utf-8"))


def _refresh_access_token(refresh_token: str) -> str:
    """Exchange a Firebase CLI refresh_token for a fresh access_token."""
    cfg = _load_firebase_config()
    client_id     = cfg.get("client_id", "563584335869-fgrhgmd47bqnekij5i8b5pr03ho849e6.apps.googleusercontent.com")
    client_secret = cfg.get("client_secret", "j9iVZfS8kkCEFUPaAeJV0sAi")

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id":     client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type":    "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _get_token() -> str:
    # 1. Explicit env var
    tok = os.environ.get("FIREBASE_TOKEN", "").strip()
    if tok:
        return tok

    cfg = _load_firebase_config()
    tokens = cfg.get("tokens", {})

    # 2. Try stored access_token (may be stale but worth trying)
    access = tokens.get("access_token", "").strip()
    refresh = tokens.get("refresh_token", "").strip()

    # 3. Auto-refresh if we have a refresh_token
    if refresh:
        try:
            print("Refreshing Firebase access token …")
            new_access = _refresh_access_token(refresh)
            # Persist so subsequent calls reuse it
            tokens["access_token"] = new_access
            cfg["tokens"] = tokens
            fb_path = Path.home() / ".config" / "configstore" / "firebase-tools.json"
            fb_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
            print("Token refreshed.")
            return new_access
        except Exception as exc:
            print(f"Auto-refresh failed: {exc}")

    if access:
        return access

    raise RuntimeError(
        "No usable Firebase token.\n"
        "Run:  firebase projects:list\n"
        "Then retry this script."
    )


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Firestore REST helpers ─────────────────────────────────────────────────────

def _from_fv(val: dict) -> Any:
    if "stringValue" in val:  return val["stringValue"]
    if "doubleValue" in val:  return float(val["doubleValue"])
    if "integerValue" in val: return int(val["integerValue"])
    if "booleanValue" in val: return val["booleanValue"]
    if "nullValue" in val:    return None
    if "arrayValue" in val:
        return [_from_fv(v) for v in val["arrayValue"].get("values", [])]
    if "mapValue" in val:
        return {k: _from_fv(v) for k, v in val["mapValue"]["fields"].items()}
    return None


def _to_fv(v: Any) -> dict:
    if v is None:         return {"nullValue": None}
    if isinstance(v, bool):  return {"booleanValue": v}
    if isinstance(v, int):   return {"integerValue": str(v)}
    if isinstance(v, float): return {"doubleValue": v}
    if isinstance(v, str):   return {"stringValue": v}
    if isinstance(v, list):
        return {"arrayValue": {"values": [_to_fv(i) for i in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: _to_fv(vv) for k, vv in v.items()}}}
    return {"stringValue": str(v)}


def _get_price_history(token: str, safe: str) -> list[dict] | None:
    url = f"{FIRESTORE_BASE}/companies/{safe}?mask.fieldPaths=price_history"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=_auth_headers(token), timeout=60)
            break
        except requests.exceptions.Timeout:
            if attempt == 2:
                raise
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    fields = resp.json().get("fields", {})
    raw = fields.get("price_history")
    if not raw:
        return []
    return _from_fv(raw)


def _patch_fields(token: str, safe: str, price_history: list, price_preview: list) -> None:
    url = (
        f"{FIRESTORE_BASE}/companies/{safe}"
        "?updateMask.fieldPaths=price_history&updateMask.fieldPaths=price_preview"
    )
    body = {
        "fields": {
            "price_history": _to_fv(price_history),
            "price_preview": _to_fv(price_preview),
        }
    }
    for attempt in range(3):
        try:
            resp = requests.patch(url, headers=_auth_headers(token), json=body, timeout=90)
            break
        except requests.exceptions.Timeout:
            if attempt == 2:
                raise
    resp.raise_for_status()


# ── Outlier detection ──────────────────────────────────────────────────────────

def _year_medians(price_history: list[dict]) -> dict[int, float]:
    """Compute median price for each calendar year represented in the data."""
    by_year: dict[int, list[float]] = {}
    for p in price_history:
        yr = int(p["date"][:4])
        by_year.setdefault(yr, []).append(float(p["price"]))
    medians: dict[int, float] = {}
    for yr, vals in by_year.items():
        s = sorted(vals)
        medians[yr] = s[len(s) // 2]
    return medians


def _clean(price_history: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Return (kept, removed).

    Strategy: two-pass year-bucket median.

    Pass 1 — global pre-screen:
      Compute the global median across ALL points. Exclude any point that is
      more than GLOBAL_PRESCREEN_FACTOR (20x) away from the global median
      before computing year medians. This handles "poisoned years" where bad
      data is the MAJORITY of a year's points (e.g. EVRD_NR 2026: 111 bad
      points at 162 KES vs. a handful of real points at 1.36 KES). Without
      the pre-screen, the 2026 year median becomes 162 KES and the algorithm
      then removes the REAL data instead of the bad data.

    Pass 2 — year-bucket filter:
      For each data point in the ORIGINAL history, compare its price to the
      median of the same calendar year computed from the pre-screened data.
      Flag points whose ratio to the year median exceeds YEAR_RATIO (6x).

    Why year-bucket for pass 2?
      - Long-term trends (KCB 267 KES in 2007 → 40 KES today) are NOT flagged
        because 267 vs the 2007 median (~250) is a ratio of ~1.07.
      - Recent spikes (BRIT_NR 90 KES spike when the 2026 median is ~10)
        give a ratio of 9x → flagged.
    """
    if len(price_history) < 5:
        return price_history, []

    # Pass 1: compute global median and pre-screen
    all_prices = sorted(float(p["price"]) for p in price_history)
    global_median = all_prices[len(all_prices) // 2]
    if global_median <= 0:
        return price_history, []

    pre_lo = global_median / GLOBAL_PRESCREEN_FACTOR
    pre_hi = global_median * GLOBAL_PRESCREEN_FACTOR
    clean_for_medians = [
        p for p in price_history
        if pre_lo <= float(p["price"]) <= pre_hi
    ]
    # Fall back to full history if pre-screen removes too much
    if len(clean_for_medians) < 5:
        clean_for_medians = price_history

    # Pass 2: compute year medians from pre-screened data, then filter original
    medians = _year_medians(clean_for_medians)

    # Fill any years that had ONLY pre-screened-out points with the nearest year's median
    all_years = sorted(set(int(p["date"][:4]) for p in price_history))
    for yr in all_years:
        if yr not in medians:
            nearest = min(medians.keys(), key=lambda y: abs(y - yr))
            medians[yr] = medians[nearest]

    lo_factor = 1.0 / YEAR_RATIO
    kept: list[dict] = []
    removed: list[dict] = []
    for p in price_history:
        yr = int(p["date"][:4])
        med = medians.get(yr, 0.0)
        if med <= 0:
            kept.append(p)
            continue
        ratio = float(p["price"]) / med
        if lo_factor <= ratio <= YEAR_RATIO:
            kept.append(p)
        else:
            removed.append(p)

    return kept, removed


# ── Main ───────────────────────────────────────────────────────────────────────

def main(dry_run: bool = False, ticker_filter: str | None = None) -> None:
    token = _get_token()
    companies = load_companies()
    if ticker_filter:
        safe_filter = ticker_filter.replace(".", "_")
        companies = [c for c in companies if c["ticker"].replace(".", "_") == safe_filter]
        if not companies:
            print(f"Ticker {ticker_filter} not found in companies list")
            return

    total_removed = 0
    changed: list[str] = []

    for company in companies:
        safe = company["ticker"].replace(".", "_")

        try:
            raw_history = _get_price_history(token, safe)
        except requests.exceptions.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 401:
                print("Token expired mid-run — re-fetching …")
                token = _get_token()
                raw_history = _get_price_history(token, safe)
            else:
                print(f"  {safe}: HTTP error — {exc}")
                continue

        if raw_history is None:
            print(f"  {safe}: document not found")
            continue
        if not raw_history:
            print(f"  {safe}: empty price_history")
            continue

        kept, removed = _clean(raw_history)

        if not removed:
            print(f"  {safe}: clean  ({len(raw_history)} pts)")
            continue

        n = len(removed)
        sample = ", ".join(
            f"{r['date']}@{r['price']}" for r in removed[:4]
        ) + ("…" if n > 4 else "")
        print(f"  {safe}: {n} outlier(s) -> {sample}")

        if not dry_run:
            price_preview = [p["price"] for p in kept[-30:]]
            _patch_fields(token, safe, kept, price_preview)

        total_removed += n
        changed.append(safe)

    print()
    print(f"Tickers with outliers : {len(changed)}")
    print(f"Total points removed  : {total_removed}")
    if changed:
        print(f"Affected              : {', '.join(changed)}")
    if dry_run:
        print("(DRY RUN — Firestore not modified)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove decimal-error spikes from Firestore price history")
    parser.add_argument("--dry-run", action="store_true", help="Report only, do not write")
    parser.add_argument("--ticker", default=None, help="Process only one ticker, e.g. BRIT_NR")
    args = parser.parse_args()
    main(dry_run=args.dry_run, ticker_filter=args.ticker)
