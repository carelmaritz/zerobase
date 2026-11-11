"""When scheduled transactions fall due (TASK-M002), on plain dates."""

from datetime import date

import pytest

from zerobase.schedules import MONTH, ONCE, WEEK, YEAR, following, occurrences


@pytest.mark.parametrize(
    ("due", "expected"),
    [
        (date(2026, 1, 31), date(2026, 2, 28)),
        (date(2026, 2, 28), date(2026, 3, 31)),  # back to the 31st
        (date(2027, 12, 31), date(2028, 1, 31)),
        (date(2028, 1, 31), date(2028, 2, 29)),  # leap year
        (date(2028, 2, 29), date(2028, 3, 31)),
        (date(2026, 3, 31), date(2026, 4, 30)),
    ],
)
def test_monthly_on_the_31st_uses_the_months_last_day(due, expected):
    assert following(MONTH, 1, 31, due) == expected


def test_monthly_on_the_30th_in_february_then_back():
    dates = occurrences(MONTH, 1, 30, date(2026, 1, 30), date(2026, 4, 30), 10)
    assert dates == [date(2026, 1, 30), date(2026, 2, 28), date(2026, 3, 30), date(2026, 4, 30)]


def test_every_three_months_across_the_year_end():
    dates = occurrences(MONTH, 3, 15, date(2026, 11, 15), date(2027, 12, 31), 10)
    assert dates == [
        date(2026, 11, 15),
        date(2027, 2, 15),
        date(2027, 5, 15),
        date(2027, 8, 15),
        date(2027, 11, 15),
    ]


def test_weekly_and_fortnightly_across_the_year_end():
    assert following(WEEK, 1, 0, date(2026, 12, 29)) == date(2027, 1, 5)
    assert following(WEEK, 2, 0, date(2026, 12, 29)) == date(2027, 1, 12)


def test_yearly_on_29_february_falls_on_the_28th_in_other_years():
    assert following(YEAR, 1, 29, date(2028, 2, 29)) == date(2029, 2, 28)
    assert following(YEAR, 1, 29, date(2031, 2, 28)) == date(2032, 2, 29)
    assert following(YEAR, 1, 3, date(2026, 3, 3)) == date(2027, 3, 3)


def test_once_has_no_next_occurrence():
    assert following(ONCE, 1, 5, date(2026, 11, 5)) is None
    assert occurrences(ONCE, 1, 5, date(2026, 11, 5), date(2030, 1, 1), 10) == [date(2026, 11, 5)]


def test_occurrences_catch_up_and_respect_the_limit():
    three = occurrences(MONTH, 1, 1, date(2026, 8, 1), date(2026, 11, 10), 100)
    assert three == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    assert len(occurrences(WEEK, 1, 0, date(1990, 1, 1), date(2026, 11, 10), 100)) == 100
    assert occurrences(MONTH, 1, 1, date(2026, 12, 1), date(2026, 11, 10), 100) == []
