from datetime import date

import pytest

from zerobase.budget import add_months, build_budget, inflow_category, parse_month
from zerobase.models import (
    Account,
    Assignment,
    Category,
    CategoryGroup,
    Transaction,
    User,
)

OCT = date(2026, 10, 1)
NOV = date(2026, 11, 1)
DEC = date(2026, 12, 1)


@pytest.fixture
def world(db):
    user = User(email="a@example.com", password_hash="x")
    db.add(user)
    db.flush()
    group = CategoryGroup(user_id=user.id, name="Needs")
    db.add(group)
    db.flush()
    groceries = Category(user_id=user.id, group_id=group.id, name="Groceries")
    account = Account(user_id=user.id, name="Current", on_budget=True)
    tracking = Account(user_id=user.id, name="Mortgage", on_budget=False)
    db.add_all([groceries, account, tracking])
    db.flush()
    inflow = inflow_category(db, user.id)
    db.commit()
    return {
        "user": user,
        "groceries": groceries,
        "inflow": inflow,
        "account": account,
        "tracking": tracking,
    }


def txn(db, w, when, amount, *, category=None, account=None):
    db.add(
        Transaction(
            user_id=w["user"].id,
            account_id=(account or w["account"]).id,
            category_id=category.id if category else None,
            date=when,
            amount=amount,
        )
    )
    db.commit()


def income(db, w, when, amount):
    txn(db, w, when, amount, category=w["inflow"])


def assign(db, w, month, amount):
    db.add(
        Assignment(user_id=w["user"].id, category_id=w["groceries"].id, month=month, amount=amount)
    )
    db.commit()


def line(view):
    return view.groups[0].lines[0]


def test_month_helpers():
    assert add_months(date(2026, 12, 1), 1) == date(2027, 1, 1)
    assert add_months(date(2026, 1, 1), -1) == date(2025, 12, 1)
    assert parse_month("2026-03", OCT) == date(2026, 3, 1)
    assert parse_month("garbage", OCT) == OCT
    assert parse_month("0001-01", OCT) == OCT
    assert parse_month(None, OCT) == OCT


def test_empty_budget(db, world):
    view = build_budget(db, world["user"].id, OCT)
    assert view.ready_to_assign == 0
    assert line(view).available == 0


def test_income_flows_to_ready_to_assign_then_envelopes(db, world):
    income(db, world, date(2026, 10, 5), 100_000)
    assert build_budget(db, world["user"].id, OCT).ready_to_assign == 100_000

    assign(db, world, OCT, 60_000)
    view = build_budget(db, world["user"].id, OCT)
    assert view.ready_to_assign == 40_000
    assert (line(view).assigned, line(view).activity, line(view).available) == (60_000, 0, 60_000)

    txn(db, world, date(2026, 10, 10), -12_000, category=world["groceries"])
    view = build_budget(db, world["user"].id, OCT)
    assert (line(view).activity, line(view).available) == (-12_000, 48_000)
    assert view.ready_to_assign == 40_000  # spending doesn't change what's unassigned


def test_positive_balance_rolls_over(db, world):
    income(db, world, date(2026, 10, 5), 100_000)
    assign(db, world, OCT, 60_000)
    txn(db, world, date(2026, 10, 10), -12_000, category=world["groceries"])

    view = build_budget(db, world["user"].id, NOV)
    assert (line(view).assigned, line(view).activity, line(view).available) == (0, 0, 48_000)
    assert view.ready_to_assign == 40_000


def test_overspending_resets_envelope_and_hits_ready_to_assign(db, world):
    income(db, world, date(2026, 10, 5), 100_000)
    assign(db, world, OCT, 60_000)
    assign(db, world, NOV, 10_000)
    txn(db, world, date(2026, 10, 10), -12_000, category=world["groceries"])
    txn(db, world, date(2026, 11, 3), -70_000, category=world["groceries"])

    nov = build_budget(db, world["user"].id, NOV)
    assert line(nov).available == -12_000  # 48,000 + 10,000 - 70,000
    assert nov.ready_to_assign == 30_000  # not yet charged to Ready to Assign

    dec = build_budget(db, world["user"].id, DEC)
    assert line(dec).available == 0
    assert dec.ready_to_assign == 18_000  # 100,000 - 70,000 assigned - 12,000 overspent


def test_future_income_and_assignments_are_ignored(db, world):
    income(db, world, date(2026, 11, 5), 50_000)
    assign(db, world, NOV, 20_000)
    view = build_budget(db, world["user"].id, OCT)
    assert view.ready_to_assign == 0
    assert line(view).available == 0


def test_tracking_accounts_stay_out_of_the_budget(db, world):
    txn(db, world, date(2026, 10, 5), 500_000, account=world["tracking"])
    txn(
        db, world, date(2026, 10, 6), -1_000, category=world["groceries"], account=world["tracking"]
    )
    view = build_budget(db, world["user"].id, OCT)
    assert view.ready_to_assign == 0
    assert line(view).activity == 0


def test_uncategorised_transactions_are_reported_and_not_counted(db, world):
    income(db, world, date(2026, 10, 4), 10_000)
    txn(db, world, date(2026, 10, 5), 4_000)  # an inflow with no category is not income
    txn(db, world, date(2026, 10, 6), -2_500)
    view = build_budget(db, world["user"].id, OCT)
    assert view.uncategorised_count == 2
    assert (view.uncategorised_outflow, view.uncategorised_inflow) == (-2_500, 4_000)
    assert view.ready_to_assign == 10_000


def test_negative_inflow_reduces_ready_to_assign(db, world):
    income(db, world, date(2026, 10, 5), 10_000)
    income(db, world, date(2026, 10, 6), -1_500)  # e.g. a salary correction
    view = build_budget(db, world["user"].id, OCT)
    assert (view.ready_to_assign, view.income_this_month) == (8_500, 8_500)
    assert view.uncategorised_count == 0


def test_inflow_category_is_not_an_envelope(db, world):
    income(db, world, date(2026, 10, 5), 10_000)
    view = build_budget(db, world["user"].id, OCT)
    names = [line.category.name for block in view.groups for line in block.lines]
    assert names == ["Groceries"]
    assert line(view).activity == 0


def test_refund_in_a_category_increases_available(db, world):
    assign(db, world, OCT, 10_000)
    txn(db, world, date(2026, 10, 6), -4_000, category=world["groceries"])
    txn(db, world, date(2026, 10, 7), 1_500, category=world["groceries"])
    assert line(build_budget(db, world["user"].id, OCT)).available == 7_500


def test_users_are_isolated(db, world):
    other = User(email="b@example.com", password_hash="x")
    db.add(other)
    db.commit()
    income(db, world, date(2026, 10, 5), 100_000)
    view = build_budget(db, other.id, OCT)
    assert view.ready_to_assign == 0
    assert view.groups == []
