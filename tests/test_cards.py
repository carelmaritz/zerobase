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


def category_picker(page: str) -> str:
    start = page.index('<select name="category_id"')
    return page[start : page.index("</select>", start)]


def test_payment_categories_cannot_be_chosen_for_transactions(client, db, setup):
    payment = setup["payment"]
    assert f'value="{payment.id}"' not in category_picker(client.get("/transactions").text)

    response = client.post(
        "/transactions",
        data={
            "account_id": setup["current"].id,
            "when": TODAY,
            "category_id": payment.id,
            "outflow": "10",
        },
    )
    assert response.status_code == 400 and "record a transfer to it" in response.text

    spend(client, setup["current"], "5", setup["groceries"])
    tesco = db.scalar(select(Transaction).where(Transaction.amount == -5_00))
    response = client.post(f"/transactions/{tesco.id}/category", data={"category_id": payment.id})
    assert response.status_code == 400


def test_the_starting_debt_keeps_its_category_when_edited(client, db, setup):
    debt = db.scalar(select(Transaction).where(Transaction.category_id == setup["payment"].id))
    form = client.get(f"/transactions/{debt.id}/edit").text
    assert f'<option value="{setup["payment"].id}" selected>Visa</option>' in form
    response = client.post(
        f"/transactions/{debt.id}/edit",
        data={
            "account_id": setup["visa"].id,
            "when": TODAY,
            "payee": "Opening debt",
            "category_id": setup["payment"].id,
            "outflow": "450",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    _, lines = view(db, setup)
    assert lines[setup["payment"].id].needed == 450_00


def test_category_management_leaves_payment_categories_alone(client, db, setup):
    payment, group = setup["payment"], setup["payment"].group_id
    for path, data in [
        (f"/categories/{payment.id}/rename", {"name": "Mine"}),
        (f"/categories/{payment.id}/hide", {"hidden": "true"}),
        (f"/categories/{payment.id}/move", {"direction": "up"}),
        (f"/categories/{payment.id}/delete", {}),
        (f"/categories/{setup['groceries']}/delete", {"target_id": payment.id}),
        (f"/categories/{setup['groceries']}/group", {"group_id": group}),
        (f"/groups/{group}/rename", {"name": "Mine"}),
        (f"/groups/{group}/move", {"direction": "down"}),
        (f"/groups/{group}/delete", {}),
    ]:
        assert client.post(path, data=data).status_code == 404, path
    assert "Credit Card Payments" not in client.get("/categories").text

    client.post("/budget/categories", data={"group_id": group, "name": "Sneaky"})
    assert db.scalar(select(Category).where(Category.name == "Sneaky")) is None
    budget_page = client.get("/budget").text
    assert "Add a category to Credit Card Payments" not in budget_page
    assert "Add a category to Bills" in budget_page


def test_renaming_a_card_renames_its_payment_category(client, db, setup):
    visa = setup["visa"]
    client.post(f"/accounts/{visa.id}/edit", data={"name": "Barclaycard", "kind": "credit_card"})
    db.expire_all()
    assert db.get(Category, setup["payment"].id).name == "Barclaycard"


def test_closing_a_card_hides_its_payment_category(client, db, setup):
    amex = add_account(client, db, "Amex", kind="credit_card")
    payment = db.scalar(select(Category).where(Category.account_id == amex.id))
    client.post(f"/accounts/{amex.id}/close", data={"closed": "true"})
    db.expire_all()
    assert db.get(Category, payment.id).hidden
    budget, _ = view(db, setup)
    assert payment.id in {ln.category.id for ln in budget.hidden}

    client.post(f"/accounts/{amex.id}/close", data={"closed": "false"})
    db.expire_all()
    assert not db.get(Category, payment.id).hidden


def test_deleting_an_empty_card_deletes_its_payment_category(client, db, setup):
    amex = add_account(client, db, "Amex", kind="credit_card")
    amex_id = amex.id
    payment_id = db.scalar(select(Category.id).where(Category.account_id == amex_id))
    response = client.post(f"/accounts/{amex_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    db.expire_all()
    assert db.get(Account, amex_id) is None and db.get(Category, payment_id) is None


def test_a_card_with_money_assigned_to_its_payment_category_is_kept(client, db, setup):
    amex = add_account(client, db, "Amex", kind="credit_card")
    payment_id = db.scalar(select(Category.id).where(Category.account_id == amex.id))
    client.post(
        "/budget/assign",
        data={"category_id": payment_id, "month": f"{MONTH:%Y-%m}", "amount": "25"},
    )
    response = client.post(f"/accounts/{amex.id}/delete")
    assert response.status_code == 400 and "Close it instead" in response.text
    db.expire_all()
    assert db.get(Category, payment_id) is not None
