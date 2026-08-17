"""Calendar rule tests."""

from datetime import date

from scheduler.calendar_util import classify_month, is_weekend_non_working, saturday_ordinal


def test_first_third_saturday_off():
    # September 2026: Sat 5=1st, 12=2nd, 19=3rd, 26=4th
    assert saturday_ordinal(date(2026, 9, 5)) == 1
    assert saturday_ordinal(date(2026, 9, 12)) == 2
    assert is_weekend_non_working(date(2026, 9, 5), [6], "first_third_off") is True
    assert is_weekend_non_working(date(2026, 9, 12), [6], "first_third_off") is False
    assert is_weekend_non_working(date(2026, 9, 19), [6], "first_third_off") is True
    assert is_weekend_non_working(date(2026, 9, 26), [6], "first_third_off") is False
    assert is_weekend_non_working(date(2026, 9, 6), [6], "first_third_off") is True  # Sunday


def test_classify_month_first_third_saturday():
    days = classify_month(2026, 9, [6], set(), {}, "first_third_off")
    by_date = {d.date: d for d in days}
    assert by_date[date(2026, 9, 5)].day_type == "NW"
    assert by_date[date(2026, 9, 12)].day_type == "W"
    assert by_date[date(2026, 9, 19)].day_type == "NW"
