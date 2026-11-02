"""Managing accounts: edit, close and reopen, delete (TASK-H004)."""

from datetime import date

import pytest
from alembic import command
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from test_migrations import engine  # noqa: F401  (fixture)
from test_web import HX, PASSWORD, category_id, register

from zerobase.migrate import alembic_config, upgrade_to_head
from zerobase.models import Account, Transaction, User
from zerobase.security import hash_password

TODAY = date.today().isoformat()


def add_account(client, db, name, opening="", on_budget=True):
    data = {"name": name, "kind": "checking", "opening_balance": opening}
    if on_budget:
        data["on_budget"] = "1"
    client.post("/accounts", data=data)
    return db.scalar(select(Account.id).where(Account.name == name))


def add_transaction(client, **data):
    return client.post("/transactions", data={"when": TODAY, **data}, follow_redirects=False)


@pytest.fixture
def accounts(client, db):
    """Current (£1,000) and Old, which received £100 of income and spent it on Groceries."""
    register(client)
    current = add_account(client, db, "Current", "1000")
    old = add_account(client, db, "Old", "100")
    add_transaction(
        client,
        account_id=old,
        payee="Tesco",
        category_id=category_id(db, "Groceries"),
        outflow="100",
    )
    return {"current": current, "old": old}


def account(db, account_id) -> Account:
    db.expire_all()
    return db.get(Account, account_id)


def account_pickers(page: str) -> str:
    """The account and transfer drop-downs of the add-transaction form."""
    start = page.index('<select name="account_id"')
    return page[start : page.index("<label>Date", start)]


def test_rename_and_kind_change_persist(client, db, accounts):
    response = client.post(
        f"/accounts/{accounts['current']}/edit",
        data={"name": "  Joint  ", "kind": "savings", "on_budget": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    saved = account(db, accounts["current"])
    assert (saved.name, saved.kind, saved.on_budget) == ("Joint", "savings", True)
    assert "Joint" in client.get("/accounts").text


def test_bad_edits_are_refused(client, db, accounts):
    current = accounts["current"]
    for data in ({"name": " ", "kind": "cash"}, {"name": "x" * 81, "kind": "cash"}):
        response = client.post(f"/accounts/{current}/edit", data=data)
        assert response.status_code == 400 and "up to 80 characters" in response.text
    response = client.post(f"/accounts/{current}/edit", data={"name": "Joint", "kind": "crypto"})
    assert response.status_code == 400
    saved = account(db, current)
    assert (saved.name, saved.kind) == ("Current", "checking")


def test_closing_needs_a_zero_balance(client, db, accounts):
    current = accounts["current"]
    response = client.post(f"/accounts/{current}/close", data={"closed": "true"})
    assert response.status_code == 400
    assert "has a balance of £1,000.00" in response.text
    assert not account(db, current).closed


def test_closing_keeps_the_budget_and_hides_the_account(client, db, accounts):
    old = accounts["old"]
    budget_before = client.get("/budget").text
    response = client.post(
        f"/accounts/{old}/close", data={"closed": "true"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert account(db, old).closed

    assert client.get("/budget").text == budget_before
    page = client.get("/accounts").text
    open_list, closed_list = page.split("Closed accounts")
    assert ">Old<" not in open_list and ">Old<" in closed_list
    assert f'value="{old}"' not in account_pickers(client.get("/transactions").text)
    history = client.get(f"/transactions?account_id={old}").text
    assert "Tesco" in history and "Starting balance" in history


def test_closed_accounts_refuse_new_transactions_and_transfers(client, db, accounts):
    old, current = accounts["old"], accounts["current"]
    client.post(f"/accounts/{old}/close", data={"closed": "true"})
    count = db.scalar(select(Transaction.id).order_by(Transaction.id.desc()))

    response = add_transaction(client, account_id=old, payee="Late", inflow="5")
    assert response.status_code == 400 and "Old is closed" in response.text
    response = add_transaction(client, account_id=current, transfer_account_id=old, outflow="5")
    assert response.status_code == 400 and "Old is closed" in response.text
    assert db.scalar(select(Transaction.id).order_by(Transaction.id.desc())) == count


def test_existing_transactions_in_a_closed_account_stay_editable(client, db, accounts):
    old = accounts["old"]
    client.post(f"/accounts/{old}/close", data={"closed": "true"})
    tesco = db.scalar(select(Transaction.id).where(Transaction.payee == "Tesco"))

    form = client.get(f"/transactions/{tesco}/edit").text
    assert f'<option value="{old}" selected>Old (closed)</option>' in form
    response = client.post(
        f"/transactions/{tesco}/edit",
        data={"account_id": old, "when": TODAY, "payee": "Tesco", "outflow": "90"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    db.expire_all()
    assert db.get(Transaction, tesco).amount == -9_000
    # The balance is no longer zero; the account stays closed and shows it.
    assert account(db, old).closed
    assert "£10.00" in client.get("/accounts").text.split("Closed accounts")[1]


def test_editing_cannot_move_a_transaction_into_a_closed_account(client, db, accounts):
    old, current = accounts["old"], accounts["current"]
    client.post(f"/accounts/{old}/close", data={"closed": "true"})
    opening = db.scalar(select(Transaction.id).where(Transaction.account_id == current))
    response = client.post(
        f"/transactions/{opening}/edit",
        data={"account_id": old, "when": TODAY, "inflow": "1000"},
    )
    assert response.status_code == 400 and "Old is closed" in response.text


def test_a_transfer_into_a_closed_account_stays_editable(client, db, accounts):
    old, current = accounts["old"], accounts["current"]
    add_transaction(client, account_id=current, transfer_account_id=old, outflow="20")
    add_transaction(client, account_id=old, transfer_account_id=current, outflow="20")
    client.post(f"/accounts/{old}/close", data={"closed": "true"})
    assert account(db, old).closed
    leg = db.scalar(
        select(Transaction.id).where(
            Transaction.account_id == current, Transaction.transfer_id.is_not(None)
        )
    )
    response = client.post(
        f"/transactions/{leg}/edit",
        data={"account_id": current, "transfer_account_id": old, "when": TODAY, "outflow": "25"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_reopen(client, db, accounts):
    old = accounts["old"]
    client.post(f"/accounts/{old}/close", data={"closed": "true"})
    assert "Reopen Old" in client.get(f"/accounts/{old}/edit").text
    client.post(f"/accounts/{old}/close", data={"closed": "false"})
    assert not account(db, old).closed
    assert f'value="{old}"' in account_pickers(client.get("/transactions").text)
    assert "Closed accounts" not in client.get("/accounts").text


def test_delete_only_without_transactions(client, db, accounts):
    current = accounts["current"]
    response = client.post(f"/accounts/{current}/delete")
    assert response.status_code == 400 and "Close it instead" in response.text
    assert account(db, current) is not None

    empty = add_account(client, db, "Mistake")
    assert "changes nothing else" in client.get(f"/accounts/{empty}/edit").text
    response = client.post(f"/accounts/{empty}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert account(db, empty) is None


def test_other_users_accounts_are_off_limits(client, db, accounts):
    other = User(email="other@example.com", password_hash=hash_password(PASSWORD))
    db.add(other)
    db.flush()
    secret = Account(user_id=other.id, name="Secret")
    db.add(secret)
    db.commit()
    secret_id = secret.id

    assert client.get(f"/accounts/{secret_id}/edit").status_code == 404
    for path, data in [
        (f"/accounts/{secret_id}/edit", {"name": "Mine", "kind": "cash"}),
        (f"/accounts/{secret_id}/close", {"closed": "true"}),
        (f"/accounts/{secret_id}/delete", {}),
    ]:
        assert client.post(path, data=data).status_code == 404, path
    saved = account(db, secret_id)
    assert (saved.name, saved.closed) == ("Secret", False)


def test_management_pages_need_login(client):
    assert client.get("/accounts/1/edit", follow_redirects=False).headers["location"] == "/login"
    response = client.post("/accounts/1/close", data={"closed": "true"}, headers=HX)
    assert response.headers["HX-Redirect"] == "/login"


def test_the_database_refuses_to_delete_an_account_with_transactions(client, db, accounts):
    if db.get_bind().dialect.name == "sqlite":
        db.execute(text("PRAGMA foreign_keys = ON"))  # off by default in SQLite
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM accounts WHERE id = :id"), {"id": accounts["current"]})


def test_0005_adds_closed_and_downgrade_keeps_transactions(engine):  # noqa: F811
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "0004")
        connection.execute(
            text(
                "INSERT INTO users (email, password_hash, created_at) "
                "VALUES ('a@b.c', 'x', '2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO accounts (user_id, name, kind, on_budget) "
                "SELECT id, 'Current', 'checking', :t FROM users"
            ),
            {"t": True},
        )
        connection.execute(
            text(
                "INSERT INTO transactions (user_id, account_id, date, payee, memo, amount) "
                "SELECT user_id, id, '2026-10-01', '', '', 500 FROM accounts"
            )
        )

    upgrade_to_head(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT closed FROM accounts")).scalar() in (False, 0)

    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0004")
        assert connection.execute(text("SELECT count(*) FROM transactions")).scalar() == 1
    assert "closed" not in {c["name"] for c in inspect(engine).get_columns("accounts")}
