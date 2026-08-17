"""Calendar utilities for working vs non-working day classification."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass(frozen=True)
class DayInfo:
    """Classification for a single calendar day."""

    date: date
    day_name: str
    is_working: bool
    day_type: str  # "W" or "NW"
    required_shifts: tuple[int, ...]


def month_dates(year: int, month: int) -> list[date]:
    """Return all dates in a month."""
    _, num_days = calendar.monthrange(year, month)
    return [date(year, month, d) for d in range(1, num_days + 1)]


def saturday_ordinal(d: date) -> int:
    """Which Saturday of the month (1-based) for a date that must be a Saturday."""
    if d.weekday() != 5:
        return 0
    return sum(1 for day in range(1, d.day + 1) if date(d.year, d.month, day).weekday() == 5)


def is_weekend_non_working(
    d: date,
    weekend_days: Iterable[int],
    saturday_rule: str = "first_third_off",
) -> bool:
    """
    Return True if date is a default non-working weekend day.

    saturday_rule:
      - first_third_off: 1st & 3rd Saturday off; 2nd/4th/5th Saturday working
      - all: every Saturday in weekend_days is off (legacy)
    """
    weekend_set = set(weekend_days)
    wd = d.weekday()
    if wd == 5:
        if saturday_rule == "first_third_off":
            return saturday_ordinal(d) in (1, 3)
        return 5 in weekend_set
    return wd in weekend_set


def classify_month(
    year: int,
    month: int,
    weekend_days: Iterable[int],
    holiday_dates: set[date],
    overrides: dict[date, bool],
    saturday_rule: str = "first_third_off",
) -> list[DayInfo]:
    """
    Classify each day in the month.

    Priority: manual override > holiday > weekend rule.
    """
    days: list[DayInfo] = []
    for d in month_dates(year, month):
        if d in overrides:
            is_working = overrides[d]
        elif d in holiday_dates:
            is_working = False
        elif is_weekend_non_working(d, weekend_days, saturday_rule):
            is_working = False
        else:
            is_working = True

        required = (2, 3) if is_working else (1, 2, 3)
        days.append(
            DayInfo(
                date=d,
                day_name=d.strftime("%A"),
                is_working=is_working,
                day_type="W" if is_working else "NW",
                required_shifts=required,
            )
        )
    return days


def expand_holidays_for_month(
    year: int,
    month: int,
    holidays: list[tuple[date, bool]],
) -> set[date]:
    """Expand yearly repeating holidays into concrete dates for the month."""
    result: set[date] = set()
    for hdate, repeats in holidays:
        if repeats:
            try:
                result.add(date(year, hdate.month, hdate.day))
            except ValueError:
                pass
        elif hdate.year == year and hdate.month == month:
            result.add(hdate)
    return result


def count_working_non_working(days: list[DayInfo]) -> tuple[int, int]:
    """Return (working_count, non_working_count)."""
    w = sum(1 for d in days if d.is_working)
    return w, len(days) - w


def dates_in_range(start: date, end: date) -> list[date]:
    """Inclusive date range."""
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out
