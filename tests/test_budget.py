from datetime import date

import pytest
from sqlalchemy import select

from zerobase.budget import (
    account_balances,
    add_months,
    build_budget,
    category_in_use,
    inflow_category,
    merge_category,
    parse_month,
)
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


def transfer(db, w, when, amount, source, target, *, category=None):
    """Move ``amount`` from ``source`` to ``target``; ``category`` goes on the budget leg."""
    legs = []
    for account, signed in ((source, -amount), (target, amount)):
        legs.append(
            Transaction(
                user_id=w["user"].id,
                account_id=account.id,
                category_id=category.id if category and account.on_budget else None,
                date=when,
                amount=signed,
            )
        )
    db.add_all(legs)
    db.flush()
    legs[0].transfer_id, legs[1].transfer_id = legs[1].id, legs[0].id
    db.commit()


@pytest.fixture
def savings(db, world):
    account = Account(user_id=world["user"].id, name="Savings", on_budget=True)
    db.add(account)
    db.commit()
    return account


def test_budget_to_budget_transfer_changes_nothing_in_the_budget(db, world, savings):
    income(db, world, date(2026, 10, 1), 100_000)
    assign(db, world, OCT, 30_000)
    transfer(db, world, date(2026, 10, 31), 50_000, world["account"], savings)
    view = build_budget(db, world["user"].id, OCT)
    assert (view.ready_to_assign, line(view).activity, line(view).available) == (70_000, 0, 30_000)
    assert view.uncategorised_count == 0
    balances = {a.name: b for a, b in account_balances(db, world["user"].id)}
    assert (balances["Current"], balances["Savings"]) == (50_000, 50_000)


def test_budget_to_tracking_transfer_is_spending(db, world):
    assign(db, world, OCT, 30_000)
    transfer(
        db,
        world,
        date(2026, 10, 5),
        20_000,
        world["account"],
        world["tracking"],
        category=world["groceries"],
    )
    view = build_budget(db, world["user"].id, OCT)
    assert (line(view).activity, line(view).available) == (-20_000, 10_000)
    assert view.uncategorised_count == 0
    balances = {a.name: b for a, b in account_balances(db, world["user"].id)}
    assert (balances["Current"], balances["Mortgage"]) == (-20_000, 20_000)


def test_tracking_to_budget_transfer_can_be_income(db, world):
    transfer(
        db,
        world,
        date(2026, 10, 5),
        15_000,
        world["tracking"],
        world["account"],
        category=world["inflow"],
    )
    view = build_budget(db, world["user"].id, OCT)
    assert (view.ready_to_assign, view.income_this_month) == (15_000, 15_000)


def test_tracking_to_tracking_transfer_stays_out_of_the_budget(db, world):
    pension = Account(user_id=world["user"].id, name="Pension", on_budget=False)
    db.add(pension)
    db.commit()
    transfer(db, world, date(2026, 10, 5), 9_000, world["tracking"], pension)
    view = build_budget(db, world["user"].id, OCT)
    assert (view.ready_to_assign, view.uncategorised_count, line(view).activity) == (0, 0, 0)


def test_uncategorised_budget_leg_to_tracking_is_still_flagged(db, world):
    # e.g. its category was deleted: the money did leave the budget, so it needs one.
    transfer(db, world, date(2026, 10, 5), 20_000, world["account"], world["tracking"])
    view = build_budget(db, world["user"].id, OCT)
    assert (view.uncategorised_count, view.uncategorised_outflow) == (1, -20_000)


# --- Hiding and merging categories (TASK-H003) ---

JAN = date(2027, 1, 1)
MONTHS = [OCT, NOV, DEC, JAN]


@pytest.fixture
def dining(db, world):
    category = Category(
        user_id=world["user"].id, group_id=world["groceries"].group_id, name="Dining out"
    )
    db.add(category)
    db.commit()
    return category


def assign_to(db, w, category, month, amount):
    db.add(Assignment(user_id=w["user"].id, category_id=category.id, month=month, amount=amount))
    db.commit()


def lines_by_name(view):
    return {ln.category.name: ln for block in view.groups for ln in block.lines}


def snapshot(db, w):
    """Ready to Assign and total Available for every test month."""
    result = []
    for month in MONTHS:
        view = build_budget(db, w["user"].id, month)
        lines = [ln for block in view.groups for ln in block.lines] + view.hidden
        result.append((view.ready_to_assign, sum(ln.available for ln in lines)))
    return result


def test_hidden_category_is_listed_apart_but_still_counts(db, world):
    income(db, world, date(2026, 10, 5), 100_000)
    assign(db, world, OCT, 60_000)
    world["groceries"].hidden = True
    db.commit()

    view = build_budget(db, world["user"].id, OCT)
    assert view.groups[0].lines == []
    assert [(ln.category.name, ln.available) for ln in view.hidden] == [("Groceries", 60_000)]
    assert view.ready_to_assign == 40_000


def test_merge_moves_transactions_and_sums_assignments_in_the_same_month(db, world, dining):
    groceries = world["groceries"]
    income(db, world, date(2026, 10, 5), 100_000)
    assign_to(db, world, groceries, OCT, 30_000)
    assign_to(db, world, dining, OCT, 20_000)
    assign_to(db, world, dining, NOV, 5_000)
    txn(db, world, date(2026, 10, 9), -4_000, category=dining)
    before = snapshot(db, world)
    groceries_id = groceries.id

    merge_category(db, dining, groceries)
    db.commit()

    rows = db.execute(
        select(Assignment.month, Assignment.amount).where(Assignment.category_id == groceries_id)
    ).all()
    assert sorted(rows) == [(OCT, 50_000), (NOV, 5_000)]
    assert db.scalar(select(Transaction.category_id).where(Transaction.amount == -4_000)) == (
        groceries_id
    )
    assert db.scalar(select(Category).where(Category.name == "Dining out")) is None
    assert snapshot(db, world) == before
    assert lines_by_name(build_budget(db, world["user"].id, OCT))["Groceries"].available == 46_000


def test_merge_drops_an_assignment_that_sums_to_zero(db, world, dining):
    assign_to(db, world, world["groceries"], OCT, 10_000)
    assign_to(db, world, dining, OCT, -10_000)
    merge_category(db, dining, world["groceries"])
    db.commit()
    assert db.scalars(select(Assignment)).all() == []


def test_merge_keeps_totals_over_several_months_without_overspending(db, world, dining):
    income(db, world, date(2026, 10, 1), 200_000)
    income(db, world, date(2026, 12, 1), 50_000)
    for month, g, d in [(OCT, 40_000, 15_000), (NOV, 10_000, 15_000), (DEC, 0, 30_000)]:
        assign_to(db, world, world["groceries"], month, g)
        assign_to(db, world, dining, month, d)
    txn(db, world, date(2026, 10, 20), -35_000, category=world["groceries"])
    txn(db, world, date(2026, 11, 20), -14_000, category=dining)
    txn(db, world, date(2026, 12, 20), 2_000, category=dining)  # refund
    before = snapshot(db, world)

    preview = build_budget(
        db, world["user"].id, JAN, merge=(dining.id, world["groceries"].id)
    ).ready_to_assign
    merge_category(db, dining, world["groceries"])
    db.commit()

    assert snapshot(db, world) == before
    assert preview == before[-1][0]


def test_merge_can_cancel_past_overspending_and_the_preview_shows_it(db, world, dining):
    income(db, world, date(2026, 10, 1), 100_000)
    assign_to(db, world, world["groceries"], OCT, 10_000)
    assign_to(db, world, dining, OCT, 10_000)
    txn(db, world, date(2026, 10, 15), -13_000, category=dining)  # 3,000 overspent
    user_id = world["user"].id
    assert build_budget(db, user_id, NOV).ready_to_assign == 77_000

    preview = build_budget(db, user_id, NOV, merge=(dining.id, world["groceries"].id))
    assert preview.ready_to_assign == 80_000  # the groceries surplus now covers it
    assert "Dining out" not in lines_by_name(preview)
    assert build_budget(db, user_id, NOV).ready_to_assign == 77_000  # the preview wrote nothing

    merge_category(db, dining, world["groceries"])
    db.commit()
    assert build_budget(db, user_id, NOV).ready_to_assign == 80_000


def test_category_in_use(db, world, dining):
    assert not category_in_use(db, dining)
    assign_to(db, world, dining, OCT, 1)
    assert category_in_use(db, dining)
    assert not category_in_use(db, world["groceries"])
    txn(db, world, date(2026, 10, 1), -1, category=world["groceries"])
    assert category_in_use(db, world["groceries"])
