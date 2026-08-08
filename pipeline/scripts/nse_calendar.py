"""
nse_calendar.py

NSE trading calendar: Monday to Friday, excluding Kenyan public holidays.

Any "missing days" or "expected sessions" figure computed on raw calendar days
is wrong and usually alarmist. The stretch from 24 December to 2 January spans
10 calendar days but only about 4 trading sessions, because weekends, Christmas,
Boxing Day and New Year all fall inside it. Gap and coverage checks must count
sessions, not dates.

HOLIDAYS
  Fixed:    1 Jan, 1 May, 1 Jun (Madaraka), 10 Oct (Huduma/Utamaduni),
            20 Oct (Mashujaa), 12 Dec (Jamhuri), 25 Dec, 26 Dec
  Movable:  Good Friday and Easter Monday, computed with Meeus/Jones/Butcher

When a public holiday falls on a Sunday, Kenya observes it on the following
Monday, so that Monday is excluded too.

KNOWN LIMITATION
  Eid al-Fitr and Eid al-Adha follow the lunar calendar and are declared by
  proclamation, so they are not derivable. They are not modelled here. Each is
  one day per year, so a gap check may over-report by up to two sessions
  annually. Anything relying on exactness should treat a 1-2 session
  discrepancy as noise rather than a defect.

  Moi Day (10 Oct) was not observed between 2010 and 2017 following the 2010
  constitution, and returned in 2018 as Huduma Day. That window is handled.
"""

from __future__ import annotations

import datetime
from functools import lru_cache

FIXED_HOLIDAYS = {
    (1, 1): "New Year's Day",
    (5, 1): "Labour Day",
    (6, 1): "Madaraka Day",
    (10, 20): "Mashujaa Day",
    (12, 12): "Jamhuri Day",
    (12, 25): "Christmas Day",
    (12, 26): "Boxing Day",
}


def _easter(year: int) -> datetime.date:
    """Gregorian Easter Sunday (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return datetime.date(year, month, day + 1)


@lru_cache(maxsize=64)
def holidays(year: int) -> frozenset[datetime.date]:
    """Kenyan public holidays for `year`, including Sunday observances."""
    out: set[datetime.date] = set()

    for (month, day) in FIXED_HOLIDAYS:
        out.add(datetime.date(year, month, day))

    # Moi Day was dropped 2010-2017, returning in 2018 as Huduma Day.
    if year < 2010 or year >= 2018:
        out.add(datetime.date(year, 10, 10))

    easter = _easter(year)
    out.add(easter - datetime.timedelta(days=2))   # Good Friday
    out.add(easter + datetime.timedelta(days=1))   # Easter Monday

    # A holiday landing on Sunday is observed the following Monday.
    for d in list(out):
        if d.weekday() == 6:
            out.add(d + datetime.timedelta(days=1))

    return frozenset(out)


def is_trading_day(d: datetime.date | str) -> bool:
    if isinstance(d, str):
        d = datetime.date.fromisoformat(d)
    return d.weekday() < 5 and d not in holidays(d.year)


def trading_days_between(start: datetime.date | str,
                         end: datetime.date | str) -> list[datetime.date]:
    """Trading sessions in (start, end) — both endpoints excluded."""
    if isinstance(start, str):
        start = datetime.date.fromisoformat(start)
    if isinstance(end, str):
        end = datetime.date.fromisoformat(end)
    out, d = [], start + datetime.timedelta(days=1)
    while d < end:
        if is_trading_day(d):
            out.append(d)
        d += datetime.timedelta(days=1)
    return out


def sessions_missed(start: datetime.date | str, end: datetime.date | str) -> int:
    """How many trading sessions sit strictly between two observed dates."""
    return len(trading_days_between(start, end))
