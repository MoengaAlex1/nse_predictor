"""Scrape the six official NSE market indices from nse.co.ke.

Source: https://www.nse.co.ke/dataservices/market-statistics/

The page renders a static HTML table under `.market-statistics-body` (or the
top-of-page cards) that carries:

    NSE ALL SHARE INDEX           value   d-day change (points)
    NSE 20 SHARE INDEX            value   d-day change (points)
    NSE 25 SHARE INDEX            value   d-day change (points)
    NSE 10 SHARE INDEX            value   d-day change (points)
    BANKING SECTOR INDEX          value   d-day change (points)
    MARKET CAPITALIZATION (Bill.) value   d-day change (billions KES)
    TOTAL SHARE TRADED            volume  d-day change (shares)
    EQUITY TURNOVER               KES     d-day change (KES)
    TOTAL EQUITY DEALS            n       d-day change (n)

The sign is expressed in CSS: ``nsecpos``/``nsecneg`` on the outer ``<td>``.
The number inside the ``<span>`` is unsigned for ``nsecpos`` and prefixed
with ``-`` for ``nsecneg`` (we handle both to be safe).

This is HTML — no OCR — and updates within the trading day (the same
~15 min delayed feed that powers the price scrape). If the NSE page is
unreachable the whole call returns ``None``; callers must fall back to
whatever they had (usually the previous day's overview doc).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

import requests

log = logging.getLogger(__name__)

NSE_STATS_URL = "https://www.nse.co.ke/dataservices/market-statistics/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nse.co.ke/",
}

# Row label (as it appears on the page, upper-case) → canonical key used
# in the market_overview.indices doc and consumed by the frontend heatmap.
_LABEL_TO_KEY: dict[str, str] = {
    "NSE ALL SHARE INDEX":            "NASI",
    "NSE 20 SHARE INDEX":             "NSE20",
    "NSE 25 SHARE INDEX":             "NSE25",
    "NSE 10 SHARE INDEX":             "NSE10",
    "BANKING SECTOR INDEX":           "NSEBSI",
    "MARKET CAPITALIZATION (BILLIONS)": "MCAP",
    "TOTAL SHARE TRADED":             "VOL",
    "EQUITY TURNOVER":                "TURNOVER",
    "TOTAL EQUITY DEALS":             "DEALS",
}

# Ordered display metadata for the six things the heatmap cares about.
# The frontend renders exactly this order; extra rows (VOL/TURNOVER/DEALS)
# are still written but the heatmap ignores them for now.
INDEX_DISPLAY_ORDER: list[tuple[str, str]] = [
    ("NASI",   "NASI"),
    ("NSE20",  "NSE 20"),
    ("NSE10",  "NSE 10"),
    ("NSE25",  "NSE 25"),
    ("NSEBSI", "NSE BSI"),
    ("MCAP",   "M.CAP"),
]

# Row-parser regex. Matches (in the wild HTML the NSE page ships):
#   <tr><td>LABEL</td>
#           <td>NUM</td><td class="nsecpos|nsecneg"><span>DELTA <i ...>
#
# The label may contain spaces, punctuation and parentheses; the value +
# delta are the two immediately following <td>s.
_ROW_RE = re.compile(
    r"<tr>\s*"
    r"<td[^>]*>\s*(?P<label>[^<]+?)\s*</td>\s*"
    r"<td[^>]*>\s*(?P<value>[\d.,\-]+)\s*</td>\s*"
    r"<td[^>]*class=\"(?P<direction>nsecpos|nsecneg)\"[^>]*>\s*"
    r"<span[^>]*>\s*(?P<delta>[\d.,\-]+)",
    re.IGNORECASE,
)


@dataclass
class IndexReading:
    key:           str      # canonical (NASI, NSE20, ...)
    label:         str      # display (NASI, NSE 20, ...)
    value:         float    # today's index level
    change_points: float    # signed raw delta vs. previous close (index units)
    change_pct:    float    # signed % change (points / prev_close * 100)

    def to_dict(self) -> dict:
        return {
            "key":           self.key,
            "label":         self.label,
            "value":         round(self.value, 4),
            "change_points": round(self.change_points, 4),
            "change_pct":    round(self.change_pct, 4),
        }


def _parse_number(s: str) -> float | None:
    """Turn '4,301.86' / '-17.96' / '21,878,434.00' into a float."""
    cleaned = s.replace(",", "").strip()
    if not cleaned or cleaned in {"-", "--"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _reading_from_row(label: str, value: float, delta: float, direction: str) -> IndexReading | None:
    """Assemble an IndexReading, resolving the sign from CSS class + normalising
    percent change against the derived previous close."""
    norm_label = re.sub(r"\s+", " ", label.strip()).upper()
    key = _LABEL_TO_KEY.get(norm_label)
    if key is None:
        return None

    # NSE encodes the sign in the CSS class. The number inside the <span>
    # is usually unsigned, but a leading '-' is occasionally present — keep
    # abs() then re-sign so we're robust to both encodings.
    signed_delta = abs(delta) * (-1.0 if direction.lower() == "nsecneg" else 1.0)
    prev_close = value - signed_delta

    if prev_close != 0:
        change_pct = (signed_delta / prev_close) * 100
    else:
        change_pct = 0.0

    # Turnover / volume / deals share the same DOM layout but they aren't
    # indices — no "%change vs previous close" interpretation. Skip pct
    # normalisation for those and let the frontend decide whether to render.
    if key in {"VOL", "TURNOVER", "DEALS"}:
        change_pct = 0.0

    display_label = dict(INDEX_DISPLAY_ORDER).get(key, key)

    return IndexReading(
        key=key,
        label=display_label,
        value=value,
        change_points=signed_delta,
        change_pct=change_pct,
    )


def parse_indices_html(html: str) -> dict[str, IndexReading]:
    """Extract every index/turnover row from a market-statistics page.

    Returns a dict keyed by canonical short (``NASI``, ``NSE20`` …).
    Rows we don't recognise are silently skipped.
    """
    out: dict[str, IndexReading] = {}
    for match in _ROW_RE.finditer(html):
        label      = match.group("label")
        value_raw  = _parse_number(match.group("value"))
        delta_raw  = _parse_number(match.group("delta"))
        direction  = match.group("direction")
        if value_raw is None or delta_raw is None:
            continue
        reading = _reading_from_row(label, value_raw, delta_raw, direction)
        if reading is None:
            continue
        out[reading.key] = reading
    return out


def fetch_market_indices(timeout: int = 20) -> dict[str, dict] | None:
    """Fetch + parse indices from nse.co.ke. Returns ``None`` on any failure.

    The return value is JSON-safe (dict of dicts) so callers can drop it
    straight into the Firestore ``market_overview.indices`` field.
    """
    try:
        resp = requests.get(NSE_STATS_URL, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        log.warning("indices: NSE market-statistics fetch failed: %s", exc)
        return None

    readings = parse_indices_html(resp.text)
    if not readings:
        log.warning("indices: 0 rows parsed from %s (page shape changed?)", NSE_STATS_URL)
        return None

    log.info("indices: parsed %d rows (%s)", len(readings), ",".join(sorted(readings.keys())))
    return {k: r.to_dict() for k, r in readings.items()}


def summarise(readings: Iterable[IndexReading]) -> str:
    """Human-friendly one-line summary — used in log lines / CLI diagnostics."""
    parts = []
    for r in readings:
        arrow = "▲" if r.change_points >= 0 else "▼"
        parts.append(f"{r.label} {r.value:,.2f} {arrow}{abs(r.change_pct):.2f}%")
    return " | ".join(parts)


if __name__ == "__main__":  # pragma: no cover — manual smoke test
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    data = fetch_market_indices()
    print(json.dumps(data, indent=2))
