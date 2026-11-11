"""Category targets, underfunded amounts and quick-assign (TASK-M001).

The maths on plain numbers is in test_target_maths.py; these go through the database and
the web routes.
"""

from datetime import date

import pytest
from sqlalchemy import select
from test_web import HX, THIS_MONTH, category_id, register

from zerobase.budget import add_months, build_budget, merge_category, month_start
from zerobase.models import (
    Account,
    Assignment,
    Category,
    CategoryGroup,
    Target,
    Transaction,
    User,
)

TODAY = date.today()
MONTH = month_start(TODAY)
NEXT = add_months(MONTH, 1)
NEXT_KEY = f"{NEXT:%Y-%m}"


@pytest.fixture
def budget(client, db):
    """A registered user with £1,000 income this month in a budget account."""
    register(client)
    client.post("/accounts", data={"name": "Current", "on_budget": "1", "opening_balance": "1000"})
    user = db.scalar(select(User))
    return {"user": user, "account": db.scalar(select(Account.id))}


def set_target(client, category, kind, amount, by="", month=THIS_MONTH):
    """``by`` is "YYYY-MM", sent as the form's separate year and month dropdowns."""
    year, _, by_month = by.partition("-")
    data = {"kind": kind, "amount": amount, "by_year": year, "by_month": by_month, "month": month}
    return client.post(f"/categories/{category}/target", data=data, follow_redirects=False)


def assign(client, category, amount, month=THIS_MONTH):
    client.post("/budget/assign", data={"category_id": category, "month": month, "amount": amount})


def spend(client, account, category, amount, when=TODAY):
    client.post(
        "/transactions",
        data={
            "account_id": account,
            "when": when.isoformat(),
            "category_id": category,
            "outflow": amount,
        },
    )


def line(db, user, name, month=MONTH):
    db.expire_all()
    view = build_budget(db, user.id, month)
    lines = [*view.hidden, *(ln for block in view.groups for ln in block.lines)]
    return next(ln for ln in lines if ln.category.name == name)


def assigned(db, category, month=MONTH):
    db.expire_all()
    return db.scalar(
        select(Assignment.amount).where(
            Assignment.category_id == category, Assignment.month == month
        )
    )


# --- Underfunded across months -------------------------------------------------------


def test_monthly_target_is_the_same_every_month_whatever_rolls_over(client, db, budget):
    groceries = category_id(db, "Groceries")
    assert set_target(client, groceries, "monthly", "400").status_code == 303
    assign(client, groceries, "150")
    assert line(db, budget["user"], "Groceries").underfunded == 250_00
    # £150 rolls into next month, but the target is to set aside £400 every month.
    assert line(db, budget["user"], "Groceries", NEXT).underfunded == 400_00


def test_balance_target_reached_by_rollover_alone_needs_nothing(client, db, budget):
    fund = category_id(db, "Emergency fund")
    set_target(client, fund, "balance", "600")
    assign(client, fund, "600")
    assert line(db, budget["user"], "Emergency fund").underfunded == 0
    assert line(db, budget["user"], "Emergency fund", NEXT).underfunded == 0


def test_overspending_resets_the_balance_so_next_month_needs_it_all(client, db, budget):
    holidays = category_id(db, "Holidays")
    set_target(client, holidays, "by_date", "1200", by=f"{add_months(MONTH, 11):%Y-%m}")
    assign(client, holidays, "100")
    spend(client, budget["account"], holidays, "150")  # overspent by £50 this month
    this = line(db, budget["user"], "Holidays")
    # Start of month after activity: −£150, so £1,350 over 12 months = £112.50 share.
    assert this.underfunded == 112_50 - 100_00
    # Overspending doesn't roll over: next month starts at £0, £1,200 over 11 months.
    assert line(db, budget["user"], "Holidays", NEXT).underfunded == 109_10


def test_target_month_already_passed_needs_the_whole_remainder(client, db, budget):
    holidays = category_id(db, "Holidays")
    set_target(client, holidays, "by_date", "300", by=f"{add_months(MONTH, -2):%Y-%m}")
    assign(client, holidays, "100")
    assert line(db, budget["user"], "Holidays").underfunded == 200_00


def test_payment_and_hidden_categories(client, db, budget):
    # A payment category can't have a target; a hidden one keeps its target.
    client.post("/accounts", data={"name": "Visa", "kind": "credit_card", "opening_balance": "0"})
    payment = db.scalar(select(Category.id).where(Category.kind == "card_payment"))
    assert set_target(client, payment, "monthly", "10").status_code == 404
    inflow = db.scalar(select(Category.id).where(Category.kind == "inflow"))
    assert set_target(client, inflow, "monthly", "10").status_code == 404

    health = category_id(db, "Health")
    set_target(client, health, "monthly", "50")
    client.post(f"/categories/{health}/hide", data={"hidden": "true"})
    hidden = line(db, budget["user"], "Health")
    assert hidden.category.hidden and hidden.underfunded == 50_00
    db.expire_all()
    assert build_budget(db, budget["user"].id, MONTH).underfunded == 0


# --- Setting targets ------------------------------------------------------------------


def test_set_edit_and_remove_a_target(client, db, budget):
    groceries = category_id(db, "Groceries")
    page = client.get(f"/budget?month={THIS_MONTH}").text
    assert f'/categories/{groceries}/target?month={THIS_MONTH}" class="muted">Set a target' in page

    set_target(client, groceries, "monthly", "400")
    page = client.get(f"/budget?month={THIS_MONTH}").text
    assert "£0.00 of £400.00 this month" in page and "Assign £400.00" in page
    assert "Underfunded this month: <strong>£400.00</strong>" in page

    form = client.get(f"/categories/{groceries}/target?month={THIS_MONTH}").text
    assert 'value="400.00"' in form and "Remove target" in form

    by = f"{add_months(MONTH, 3):%Y-%m}"
    set_target(client, groceries, "by_date", "800", by=by)
    form = client.get(f"/categories/{groceries}/target?month={THIS_MONTH}").text
    picked = add_months(MONTH, 3)
    assert f'<option value="{picked.month}" selected>{picked:%B}</option>' in form
    assert f'<option value="{picked.year}" selected>{picked.year}</option>' in form
    db.expire_all()
    target = db.scalar(select(Target))
    assert (target.kind, target.amount, target.month) == ("by_date", 800_00, add_months(MONTH, 3))
    assert db.scalar(select(Target.id).where(Target.id != target.id)) is None  # one per category

    gone = client.post(
        f"/categories/{groceries}/target/delete", data={"month": THIS_MONTH}, follow_redirects=False
    )
    assert gone.status_code == 303
    db.expire_all()
    assert db.scalar(select(Target)) is None


@pytest.mark.parametrize(
    ("kind", "amount", "by", "message"),
    [
        ("monthly", "0", "", "more than zero"),
        ("monthly", "-5", "", "more than zero"),
        ("monthly", "abc", "", "not a valid amount"),
        ("by_date", "100", "", "Choose the month"),
        ("by_date", "100", "2026-13", "Choose the month"),
        ("weekly", "100", "", "Choose a kind"),
    ],
)
def test_bad_targets_are_refused(client, db, budget, kind, amount, by, message):
    response = set_target(client, category_id(db, "Groceries"), kind, amount, by=by)
    assert response.status_code == 400 and message in response.text
    db.expire_all()
    assert db.scalar(select(Target)) is None


def test_other_users_categories_are_off_limits(client, db, budget):
    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.flush()
    group = CategoryGroup(user_id=other.id, name="Private")
    db.add(group)
    db.flush()
    secret = Category(user_id=other.id, group_id=group.id, name="Secret")
    db.add(secret)
    db.flush()
    db.add(Target(user_id=other.id, category_id=secret.id, kind="monthly", amount=400_00))
    db.commit()
    secret_id = secret.id

    assert set_target(client, secret_id, "monthly", "1").status_code == 404
    assert client.get(f"/categories/{secret_id}/target").status_code == 404
    assert client.post(f"/categories/{secret_id}/target/delete").status_code == 404
    fund = client.post("/budget/fund", data={"category_id": secret_id, "month": THIS_MONTH})
    assert fund.status_code == 404
    db.expire_all()
    assert db.scalar(select(Target.amount)) == 400_00
    assert db.scalar(select(Assignment.id)) is None


# --- Merging and deleting ---------------------------------------------------------------


def test_merge_keeps_the_target_categorys_own_target(client, db, budget):
    dining, groceries = category_id(db, "Dining out"), category_id(db, "Groceries")
    set_target(client, dining, "monthly", "100")
    set_target(client, groceries, "monthly", "400")
    merge_category(db, db.get(Category, dining), db.get(Category, groceries))
    db.commit()
    assert [(t.category_id, t.amount) for t in db.scalars(select(Target))] == [(groceries, 400_00)]


def test_merge_moves_the_target_when_the_other_has_none(client, db, budget):
    dining, groceries = category_id(db, "Dining out"), category_id(db, "Groceries")
    set_target(client, dining, "balance", "100")
    client.post(f"/categories/{dining}/delete", data={"target_id": groceries})
    db.expire_all()
    assert [(t.category_id, t.kind) for t in db.scalars(select(Target))] == [(groceries, "balance")]


def test_deleting_an_unused_category_deletes_its_target(client, db, budget):
    dining = category_id(db, "Dining out")
    set_target(client, dining, "monthly", "100")
    client.post(f"/categories/{dining}/delete", data={"target_id": ""})
    db.expire_all()
    assert db.get(Category, dining) is None
    assert db.scalar(select(Target)) is None


# --- Quick-assign -------------------------------------------------------------------------


def test_assign_one_category_updates_the_figures_and_its_input(client, db, budget):
    groceries = category_id(db, "Groceries")
    set_target(client, groceries, "monthly", "400")
    assign(client, groceries, "150")
    response = client.post(
        "/budget/fund", data={"category_id": groceries, "month": THIS_MONTH}, headers=HX
    )
    assert response.status_code == 200
    assert assigned(db, groceries) == 400_00
    assert f'id="assign-{groceries}"' in response.text and 'value="400.00"' in response.text
    assert "£400.00 of £400.00 this month" in response.text and "funded" in response.text
    assert line(db, budget["user"], "Groceries").underfunded == 0


def test_assign_all_stops_when_ready_to_assign_runs_out(client, db, budget):
    # £1,000 to assign; targets need £400 + £500 + £300, in budget order.
    first, second, third = "Groceries", "Transport", "Emergency fund"
    set_target(client, category_id(db, first), "monthly", "400")
    set_target(client, category_id(db, second), "monthly", "500")
    set_target(client, category_id(db, third), "balance", "300")
    response = client.post("/budget/fund-all", data={"month": THIS_MONTH}, headers=HX)
    assert "ran out before these were fully funded: Emergency fund." in response.text
    assert assigned(db, category_id(db, first)) == 400_00
    assert assigned(db, category_id(db, second)) == 500_00
    assert assigned(db, category_id(db, third)) == 100_00
    db.expire_all()
    view = build_budget(db, budget["user"].id, MONTH)
    assert view.ready_to_assign == 0 and view.underfunded == 200_00

    # Nothing left: a second press assigns nothing and Ready to Assign stays at £0.
    client.post("/budget/fund-all", data={"month": THIS_MONTH}, headers=HX)
    assert assigned(db, category_id(db, third)) == 100_00
    db.expire_all()
    assert build_budget(db, budget["user"].id, MONTH).ready_to_assign == 0


def test_assign_all_skips_hidden_categories(client, db, budget):
    health, groceries = category_id(db, "Health"), category_id(db, "Groceries")
    set_target(client, health, "monthly", "50")
    set_target(client, groceries, "monthly", "60")
    client.post(f"/categories/{health}/hide", data={"hidden": "true"})
    client.post("/budget/fund-all", data={"month": THIS_MONTH}, follow_redirects=False)
    assert assigned(db, groceries) == 60_00
    assert assigned(db, health) is None


def test_quick_assign_is_capped_by_a_later_months_ready_to_assign(client, db, budget):
    # Next month already has £900 assigned, so only £100 can go this month.
    assign(client, category_id(db, "Transport"), "900", month=NEXT_KEY)
    groceries = category_id(db, "Groceries")
    set_target(client, groceries, "monthly", "400")
    response = client.post("/budget/fund", data={"category_id": groceries, "month": THIS_MONTH})
    assert response.status_code == 400 and "ran out" in response.text
    assert assigned(db, groceries) == 100_00
    db.expire_all()
    assert build_budget(db, budget["user"].id, NEXT).ready_to_assign == 0


def test_quick_assign_with_nothing_to_assign_changes_nothing(client, db, budget):
    groceries = category_id(db, "Groceries")
    set_target(client, groceries, "monthly", "400")
    assign(client, category_id(db, "Transport"), "1000")
    response = client.post(
        "/budget/fund", data={"category_id": groceries, "month": THIS_MONTH}, headers=HX
    )
    assert "ran out" in response.text
    assert assigned(db, groceries) is None


def test_a_funded_category_has_nothing_to_quick_assign(client, db, budget):
    groceries = category_id(db, "Groceries")
    set_target(client, groceries, "monthly", "400")
    assign(client, groceries, "400")
    response = client.post(
        "/budget/fund", data={"category_id": groceries, "month": THIS_MONTH}, follow_redirects=False
    )
    assert response.status_code == 303
    assert assigned(db, groceries) == 400_00


def test_redirect_after_plain_form_assign_all(client, db, budget):
    set_target(client, category_id(db, "Groceries"), "monthly", "10")
    response = client.post("/budget/fund-all", data={"month": THIS_MONTH}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == f"/budget?month={THIS_MONTH}"


def test_transactions_unaffected(client, db, budget):
    # Quick-assign moves money between envelopes only.
    set_target(client, category_id(db, "Groceries"), "monthly", "10")
    before = db.scalar(select(Transaction.id).order_by(Transaction.id.desc()))
    client.post("/budget/fund-all", data={"month": THIS_MONTH})
    db.expire_all()
    assert db.scalar(select(Transaction.id).order_by(Transaction.id.desc())) == before
