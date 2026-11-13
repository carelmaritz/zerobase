"""Target maths on plain numbers (TASK-M001).

Each case is a worked example from the agreed plan in TASKS/TASK-M001.md. Amounts are
pence; ``available`` is the category's Available at the end of the month shown.
"""

from datetime import date

import pytest

from zerobase.budget import underfunded
from zerobase.models import BALANCE, BY_DATE, MONTHLY

NOV_26, JUL_27, AUG_27 = date(2026, 11, 1), date(2027, 7, 1), date(2027, 8, 1)


@pytest.mark.parametrize(
    ("assigned", "available", "needed"),
    [
        (0, 0, 400_00),
        (150_00, 150_00, 250_00),
        (500_00, 500_00, 0),
        # Leftovers and overspending make no difference: it's £400 every month.
        (0, 900_00, 400_00),
        (100_00, -50_00, 300_00),
    ],
)
def test_monthly_sets_aside_the_amount_every_month(assigned, available, needed):
    assert underfunded(MONTHLY, 400_00, None, NOV_26, assigned, available) == needed


@pytest.mark.parametrize(
    ("assigned", "available", "needed"),
    [
        (0, 1_200_00, 1_800_00),
        (0, 3_000_00, 0),  # reached by rollover alone
        (0, 3_500_00, 0),
        (100_00, -50_00, 3_050_00),  # overspent: the overspending needs covering too
    ],
)
def test_balance_needs_the_gap_to_the_target(assigned, available, needed):
    assert underfunded(BALANCE, 3_000_00, None, NOV_26, assigned, available) == needed


@pytest.mark.parametrize(
    ("month", "assigned", "start", "needed"),
    [
        (NOV_26, 0, 300_00, 100_00),  # 9 months left, £900 to go
        (NOV_26, 40_00, 300_00, 60_00),
        (NOV_26, 150_00, 300_00, 0),  # more than this month's share
        (JUL_27, 0, 1_100_00, 100_00),  # the target month: 1 month left
        (AUG_27, 0, 1_100_00, 100_00),  # date passed: the whole remainder
        (AUG_27, 30_00, 1_100_00, 70_00),
        (NOV_26, 0, 1_200_00, 0),  # already there
        (NOV_26, 0, -60_00, 140_00),  # overspent this month: £1,260 over 9 months
    ],
)
def test_by_date_spreads_the_remainder_over_the_months_left(month, assigned, start, needed):
    available = start + assigned
    assert underfunded(BY_DATE, 1_200_00, JUL_27, month, assigned, available) == needed


def test_by_date_rounds_the_monthly_share_up_to_the_penny():
    jan = date(2027, 1, 1)
    assert underfunded(BY_DATE, 1_000_00, jan, NOV_26, 0, 0) == 333_34


def test_by_date_share_stays_put_while_assigning_this_month():
    # Assigning part of the share must not shrink the share itself.
    jan = date(2027, 1, 1)
    for assigned in (0, 100_00, 333_34):
        assert underfunded(BY_DATE, 1_000_00, jan, NOV_26, assigned, assigned) == max(
            0, 333_34 - assigned
        )


# Repeating (yearly) by-month targets: TASK-M002's Dropbox example, £120 due in March.
MAR_26, APR_26, FEB_27, MAR_27, APR_27 = (
    date(2026, 3, 1),
    date(2026, 4, 1),
    date(2027, 2, 1),
    date(2027, 3, 1),
    date(2027, 4, 1),
)


def yearly(month, assigned, available, activity=0, by=MAR_26):
    return underfunded(
        BY_DATE, 120_00, by, month, assigned, available, repeats=True, activity=activity
    )


def test_repeating_target_rolls_on_to_next_year():
    assert yearly(APR_26, 0, 0) == 10_00  # 12 months to March 2027
    assert yearly(FEB_27, 0, 100_00) == 10_00  # £20 to go over 2 months
    assert yearly(MAR_27, 0, 110_00) == 10_00  # due this month


def test_paying_the_bill_in_its_month_doesnt_make_it_underfunded():
    # £110 carried in, £10 assigned, the £120 renewal paid: £0 left, nothing needed.
    assert yearly(MAR_27, 10_00, 0, activity=-120_00) == 0
    assert yearly(APR_27, 0, 0) == 10_00  # and next year starts again


def test_repeating_target_isnt_due_before_its_first_month():
    # Set up for March 2028: seen from April 2026 that's 24 months away, not 12.
    assert yearly(APR_26, 0, 0, by=date(2028, 3, 1)) == 5_00


def test_one_off_target_still_counts_this_months_spending():
    jul = date(2027, 7, 1)
    # Not repeating: spending this month raises what's needed, as in M001.
    needed = underfunded(BY_DATE, 120_00, jul, jul, 0, -20_00, activity=-20_00)
    assert needed == 140_00
