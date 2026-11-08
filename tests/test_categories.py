"""Managing categories and groups (TASK-H003)."""

from datetime import date

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from test_web import HX, PASSWORD, THIS_MONTH, category_id, register

from zerobase.budget import add_months, month_start
from zerobase.models import Account, Assignment, Category, CategoryGroup, Transaction, User
from zerobase.security import hash_password


@pytest.fixture
def budget(client, db):
    """A registered user with £1,000 in Current, £300 assigned to Groceries, £50 spent."""
    register(client)
    client.post("/accounts", data={"name": "Current", "on_budget": "1", "opening_balance": "1000"})
    groceries = category_id(db, "Groceries")
    client.post(
        "/budget/assign", data={"category_id": groceries, "month": THIS_MONTH, "amount": "300"}
    )
    account = db.scalar(select(Account.id))
    client.post(
        "/transactions",
        data={
            "account_id": account,
            "when": date.today().isoformat(),
            "payee": "Tesco",
            "category_id": groceries,
            "outflow": "50",
        },
    )
    return {"groceries": groceries, "account": account}


def group_id(db, name):
    return db.scalar(select(CategoryGroup.id).where(CategoryGroup.name == name))


def names_in_order(page: str, *names: str) -> bool:
    positions = [page.index(name) for name in names]
    return positions == sorted(positions)


def test_rename_reorder_and_move_show_in_the_budget_and_picker(client, db, budget):
    groceries = budget["groceries"]
    client.post(f"/categories/{groceries}/rename", data={"name": "  Food shop  "})
    client.post(f"/categories/{category_id(db, 'Health')}/move", data={"direction": "up"})
    client.post(f"/groups/{group_id(db, 'Wants')}/move", data={"direction": "up"})
    client.post(f"/groups/{group_id(db, 'Bills')}/rename", data={"name": "Fixed costs"})
    client.post(
        f"/categories/{category_id(db, 'Holidays')}/group", data={"group_id": group_id(db, "Needs")}
    )

    for page in (client.get("/budget").text, client.get("/transactions").text):
        assert "Food shop" in page and "Groceries" not in page
        assert names_in_order(page, "Fixed costs", "Wants", "Needs", "Savings goals")
        assert names_in_order(page, "Food shop", "Health", "Transport", "Holidays")
        assert names_in_order(page, "Savings goals", "Emergency fund")
    assert "Holidays" not in client.get("/budget").text.split("Savings goals")[1]


def test_reorder_at_the_edges_is_harmless(client, db, budget):
    first = category_id(db, "Rent / Mortgage")
    assert client.post(f"/categories/{first}/move", data={"direction": "up"}).status_code == 200
    bad = client.post(f"/categories/{first}/move", data={"direction": "sideways"})
    assert bad.status_code == 422
    page = client.get("/budget").text
    assert names_in_order(page, "Rent / Mortgage", "Utilities", "Phone &amp; Internet")


def test_invalid_names_are_refused(client, db, budget):
    groceries = budget["groceries"]
    response = client.post(f"/categories/{groceries}/rename", data={"name": "   "})
    assert response.status_code == 400 and "1 to 60 characters" in response.text
    response = client.post(f"/groups/{group_id(db, 'Needs')}/rename", data={"name": "x" * 61})
    assert response.status_code == 400
    db.expire_all()
    assert db.get(Category, groceries).name == "Groceries"


def test_hiding_keeps_the_money_and_says_where_it_went(client, db, budget):
    groceries = budget["groceries"]
    before = client.get("/budget").text
    assert "£700.00" in before  # Ready to Assign

    hidden = client.post(f"/categories/{groceries}/hide", data={"hidden": "true"})
    assert hidden.status_code == 200
    assert "Groceries still has £250.00 available" in hidden.text

    page = client.get("/budget").text
    assert "£700.00" in page
    groups, hidden_section = page.split("Hidden categories (1)")
    assert "Groceries" not in groups and "£250.00" in hidden_section
    add_form = client.get("/transactions").text.split('<form method="get"')[0]
    assert f'value="{groceries}"' not in add_form

    # A transaction already in the hidden category keeps it when edited.
    tesco = db.scalar(select(Transaction.id).where(Transaction.payee == "Tesco"))
    edit_form = client.get(f"/transactions/{tesco}/edit").text
    assert f'<option value="{groceries}" selected>Groceries</option>' in edit_form

    client.post(f"/categories/{groceries}/hide", data={"hidden": "false"})
    assert "Hidden categories" not in client.get("/budget").text


def test_hiding_an_empty_category_needs_no_notice(client, db, budget):
    response = client.post(
        f"/categories/{category_id(db, 'Health')}/hide",
        data={"hidden": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_unused_category_deletes_without_a_target(client, db, budget):
    health = category_id(db, "Health")
    assert "nothing else changes" in client.get(f"/categories/{health}/delete").text
    client.post(f"/categories/{health}/delete")
    assert category_id(db, "Health") is None


def test_used_category_needs_a_target(client, db, budget):
    response = client.post(f"/categories/{budget['groceries']}/delete")
    assert response.status_code == 400 and "Choose where they should go" in response.text
    assert category_id(db, "Groceries") == budget["groceries"]


def test_delete_with_a_target_previews_then_merges(client, db, budget):
    groceries, dining = budget["groceries"], category_id(db, "Dining out")
    client.post("/budget/assign", data={"category_id": dining, "month": THIS_MONTH, "amount": "20"})

    preview = client.get(f"/categories/{groceries}/delete?target_id={dining}").text
    assert "stays at £680.00" in preview
    response = client.post(
        f"/categories/{groceries}/delete", data={"target_id": dining}, follow_redirects=False
    )
    assert response.status_code == 303

    db.expire_all()
    assert category_id(db, "Groceries") is None
    assert db.scalar(select(Transaction.category_id).where(Transaction.payee == "Tesco")) == dining
    rows = db.execute(select(Assignment.category_id, Assignment.amount)).all()
    assert rows == [(dining, 32_000)]
    page = client.get("/budget").text
    assert "£680.00" in page and "£270.00" in page


def test_preview_shows_a_change_in_ready_to_assign(client, db, budget):
    groceries, dining = budget["groceries"], category_id(db, "Dining out")
    last_month = add_months(month_start(date.today()), -1)
    client.post(
        "/budget/assign",
        data={"category_id": groceries, "month": f"{last_month:%Y-%m}", "amount": "100"},
    )
    client.post(
        "/transactions",
        data={
            "account_id": budget["account"],
            "when": last_month.isoformat(),
            "payee": "Restaurant",
            "category_id": dining,
            "outflow": "30",
        },
    )
    # Last month: Dining out overspent by £30; Groceries had £100 spare.
    preview = client.get(f"/categories/{dining}/delete?target_id={groceries}").text
    assert "changes from £570.00 to <strong>£600.00</strong>" in preview


def test_inflow_category_cannot_be_managed_or_merged_into(client, db, budget):
    user = db.scalar(select(User))
    inflow = db.scalar(
        select(Category.id).where(Category.user_id == user.id, Category.kind == "inflow")
    )
    for path, data in [
        (f"/categories/{inflow}/rename", {"name": "Mine"}),
        (f"/categories/{inflow}/hide", {"hidden": "true"}),
        (f"/categories/{inflow}/move", {"direction": "up"}),
        (f"/categories/{inflow}/delete", {}),
        (f"/categories/{budget['groceries']}/delete", {"target_id": inflow}),
    ]:
        assert client.post(path, data=data).status_code == 404, path
    assert client.get(f"/categories/{inflow}/delete").status_code == 404


def test_a_group_deletes_only_when_empty(client, db, budget):
    needs = group_id(db, "Savings goals")
    response = client.post(f"/groups/{needs}/delete")
    assert response.status_code == 400 and "Move or delete the categories" in response.text
    for name in ("Emergency fund", "Holidays"):
        client.post(f"/categories/{category_id(db, name)}/delete")
    assert "Delete group" in client.get("/categories").text
    client.post(f"/groups/{needs}/delete")
    assert group_id(db, "Savings goals") is None


def test_other_users_categories_and_groups_are_off_limits(client, db, budget):
    other = User(email="other@example.com", password_hash=hash_password(PASSWORD))
    db.add(other)
    db.flush()
    group = CategoryGroup(user_id=other.id, name="Private")
    db.add(group)
    db.flush()
    secret = Category(user_id=other.id, group_id=group.id, name="Secret")
    db.add(secret)
    db.commit()
    mine = budget["groceries"]

    for path, data in [
        (f"/categories/{secret.id}/rename", {"name": "Mine"}),
        (f"/categories/{secret.id}/move", {"direction": "up"}),
        (f"/categories/{secret.id}/hide", {"hidden": "true"}),
        (f"/categories/{secret.id}/delete", {}),
        (f"/categories/{mine}/delete", {"target_id": secret.id}),
        (f"/categories/{mine}/group", {"group_id": group.id}),
        (f"/groups/{group.id}/rename", {"name": "Mine"}),
        (f"/groups/{group.id}/move", {"direction": "up"}),
        (f"/groups/{group.id}/delete", {}),
    ]:
        assert client.post(path, data=data).status_code == 404, path
    assert client.get(f"/categories/{mine}/delete?target_id={secret.id}").status_code == 404
    assert (
        "Secret" not in client.get("/categories").text
        and "Private" not in client.get("/categories").text
    )


def test_management_pages_need_login(client):
    assert client.get("/categories", follow_redirects=False).headers["location"] == "/login"
    response = client.post("/categories/1/rename", data={"name": "x"}, headers=HX)
    assert response.headers["HX-Redirect"] == "/login"


def test_the_database_refuses_to_delete_a_category_with_transactions(client, db, budget):
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("PRAGMA foreign_keys = ON"))  # off by default in SQLite
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM categories WHERE id = :id"), {"id": budget["groceries"]})
