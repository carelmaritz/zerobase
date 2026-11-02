"""Credit cards through the app: creation, spending, payments, refunds (TASK-H005)."""

from datetime import date

import pytest
from sqlalchemy import select
from test_web import category_id, register

from zerobase.budget import build_budget, month_start
from zerobase.models import Account, Category, CategoryGroup, Transaction, User

TODAY = date.today().isoformat()
MONTH = month_start(date.today())


def add_account(client, db, name, opening="", kind="checking", on_budget=True):
    data = {"name": name, "kind": kind, "opening_balance": opening}
    if on_budget:
        data["on_budget"] = "1"
    client.post("/accounts", data=data)
    return db.scalar(select(Account).where(Account.name == name))


def spend(client, account, amount, category=None, transfer=None, inflow=False):
    data = {"account_id": account.id, "when": TODAY, "inflow" if inflow else "outflow": amount}
    if category:
        data["category_id"] = category
    if transfer:
        data["transfer_account_id"] = transfer.id
    response = client.post("/transactions", data=data, follow_redirects=False)
    assert response.status_code == 303, response.text
    return response


@pytest.fixture
def setup(client, db):
    """Current £1,000; Visa with £500 of starting debt; £100 assigned to Groceries."""
    register(client)
    current = add_account(client, db, "Current", "1000")
    visa = add_account(client, db, "Visa", "-500", kind="credit_card", on_budget=False)
    groceries = category_id(db, "Groceries")
    client.post(
        "/budget/assign",
        data={"category_id": groceries, "month": f"{MONTH:%Y-%m}", "amount": "100"},
    )
    user = db.scalar(select(User))
    payment = db.scalar(select(Category).where(Category.account_id == visa.id))
    return {
        "user": user,
        "current": current,
        "visa": visa,
        "groceries": groceries,
        "payment": payment,
    }


def view(db, s):
    db.expire_all()
    budget = build_budget(db, s["user"].id, MONTH)
    lines = {ln.category.id: ln for g in budget.groups for ln in g.lines}
    lines.update({ln.category.id: ln for ln in budget.hidden})
    return budget, lines


def test_creating_a_card_makes_its_payment_category(client, db, setup):
    visa, payment = setup["visa"], setup["payment"]
    assert visa.on_budget and visa.is_credit_card  # on_budget forced, though unticked
    assert payment.is_card_payment and payment.name == "Visa"
    group = db.get(CategoryGroup, payment.group_id)
    assert (group.kind, group.name) == ("card_payments", "Credit Card Payments")

    budget, lines = view(db, setup)
    assert budget.groups[0].group.id == group.id  # listed first
    assert budget.ready_to_assign == 900_00  # the debt doesn't touch Ready to Assign
    line = lines[payment.id]
    assert (line.available, line.activity, line.needed) == (0, 0, 500_00)
    assert budget.uncategorised_count == 0


def test_a_second_card_shares_the_system_group(client, db, setup):
    amex = add_account(client, db, "Amex", kind="credit_card")
    amex_payment = db.scalar(select(Category).where(Category.account_id == amex.id))
    assert amex_payment.group_id == setup["payment"].group_id
    groups = db.scalars(select(CategoryGroup).where(CategoryGroup.kind == "card_payments"))
    assert len(groups.all()) == 1


def test_a_card_in_credit_is_money_to_assign(client, db, setup):
    add_account(client, db, "Overpaid", "50", kind="credit_card")
    budget, _ = view(db, setup)
    assert budget.ready_to_assign == 950_00


def test_card_spending_moves_money_to_the_payment_category(client, db, setup):
    spend(client, setup["visa"], "30", setup["groceries"])
    budget, lines = view(db, setup)
    assert lines[setup["groceries"]].available == 70_00
    payment = lines[setup["payment"].id]
    assert (payment.activity, payment.available, payment.needed) == (30_00, 30_00, 500_00)
    assert budget.ready_to_assign == 900_00


def test_overspending_on_the_card_is_credit_overspending(client, db, setup):
    spend(client, setup["visa"], "120", setup["groceries"])
    _, lines = view(db, setup)
    groceries = lines[setup["groceries"]]
    assert (groceries.available, groceries.credit_overspent, groceries.cash_overspent) == (
        -20_00,
        20_00,
        0,
    )
    assert lines[setup["payment"].id].available == 100_00


def test_paying_the_card_from_current(client, db, setup):
    spend(client, setup["visa"], "30", setup["groceries"])
    spend(client, setup["current"], "30", transfer=setup["visa"])
    budget, lines = view(db, setup)
    payment = lines[setup["payment"].id]
    assert (payment.activity, payment.available, payment.needed) == (0, 0, 500_00)
    assert budget.uncategorised_count == 0
    visa_balance = db.scalar(
        select(Transaction.amount).where(
            Transaction.account_id == setup["visa"].id, Transaction.transfer_id.is_not(None)
        )
    )
    assert visa_balance == 30_00


def test_a_refund_on_the_card(client, db, setup):
    spend(client, setup["visa"], "30", setup["groceries"])
    spend(client, setup["visa"], "10", setup["groceries"], inflow=True)
    _, lines = view(db, setup)
    assert lines[setup["groceries"]].available == 80_00
    assert lines[setup["payment"].id].available == 20_00


def test_a_card_cannot_change_type_and_nothing_can_become_one(client, db, setup):
    visa, current = setup["visa"], setup["current"]
    response = client.post(f"/accounts/{visa.id}/edit", data={"name": "Visa", "kind": "checking"})
    assert response.status_code == 400
    response = client.post(
        f"/accounts/{current.id}/edit", data={"name": "Current", "kind": "credit_card"}
    )
    assert response.status_code == 400
    db.expire_all()
    assert (db.get(Account, visa.id).kind, db.get(Account, current.id).kind) == (
        "credit_card",
        "checking",
    )
    page = client.get(f"/accounts/{current.id}/edit").text
    assert 'value="credit_card"' not in page
