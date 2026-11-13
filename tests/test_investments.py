"""Investment accounts and "Update value" (TASK-M007)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from test_web import PASSWORD, category_id, register

from zerobase.budget import build_budget, month_start
from zerobase.investments import parse_quantity, parse_symbol
from zerobase.models import CLEARED, Account, Transaction, User
from zerobase.routers.valuation import VALUE_PAYEE
from zerobase.security import hash_password

TODAY = date.today()


# --- parsing ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [("btc", "BTC"), (" Sol ", "SOL"), ("1INCH", "1INCH"), ("", None), ("  ", None)],
)
def test_symbols_are_saved_in_capitals(text, expected):
    assert parse_symbol(text) == expected


@pytest.mark.parametrize("text", ["BT C", "BTC!", "ABCDEFGHIJK", "£"])
def test_bad_symbols_are_refused(text):
    with pytest.raises(ValueError, match="Coin"):
        parse_symbol(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.25", "0.25"),
        ("0.2500", "0.25"),
        ("1,000.5", "1000.5"),
        ("100", "100"),
        ("1e2", "100"),
        ("0.000000000000000001", "0.000000000000000001"),
        ("0", "0"),
        ("-0", "0"),
        ("", None),
    ],
)
def test_amounts_held_are_exact(text, expected):
    value = parse_quantity(text)
    assert (None if value is None else format(value, "f")) == expected


@pytest.mark.parametrize(
    "text", ["abc", "-1", "nan", "inf", "0.0000000000000000001", "1" + "0" * 20]
)
def test_bad_amounts_are_refused(text):
    with pytest.raises(ValueError, match="Amount held"):
        parse_quantity(text)


# --- accounts --------------------------------------------------------------------------


def add(client, db, name, kind, *, opening="", on_budget=True, **extra):
    data = {"name": name, "kind": kind, "opening_balance": opening, **extra}
    if on_budget:
        data["on_budget"] = "1"
    response = client.post("/accounts", data=data, follow_redirects=False)
    return response, db.scalar(select(Account).where(Account.name == name))


@pytest.fixture
def me(client, db):
    register(client)
    client.post(
        "/accounts",
        data={"name": "Current", "kind": "checking", "on_budget": "1", "opening_balance": "1000"},
    )
    return db.scalar(select(User))


def ready(db, user) -> int:
    db.expire_all()
    return build_budget(db, user.id, month_start(TODAY)).ready_to_assign


@pytest.mark.parametrize("kind", ["crypto", "pension", "isa_stocks"])
def test_investment_accounts_are_always_tracking(client, db, me, kind):
    before = ready(db, me)
    response, account = add(client, db, "Invest", kind, opening="5000", on_budget=True)
    assert response.status_code == 303
    assert account.kind == kind and not account.on_budget
    assert ready(db, me) == before  # the opening value isn't money to assign
    start = db.scalar(select(Transaction).where(Transaction.account_id == account.id))
    assert start.amount == 500000 and start.category_id is None


def test_crypto_keeps_its_coin_and_amount(client, db, me):
    _, account = add(client, db, "Coinbase BTC", "crypto", symbol="btc", quantity="0.2500")
    assert account.symbol == "BTC" and account.quantity == Decimal("0.25")
    assert account.holding == "0.25 BTC"
    page = client.get("/accounts").text
    assert 'Coinbase BTC</a> <small class="muted">· 0.25 BTC</small>' in page


def test_other_kinds_ignore_coin_fields(client, db, me):
    _, account = add(client, db, "Vanguard", "pension", symbol="BTC", quantity="1")
    assert account.symbol is None and account.quantity is None


def test_bad_coin_fields_are_refused_on_add(client, db, me):
    response, account = add(client, db, "Bad", "crypto", symbol="B T C")
    assert response.status_code == 400 and account is None
    assert "Coin: use the trading symbol" in response.text
    response, account = add(client, db, "Bad", "crypto", quantity="-1")
    assert response.status_code == 400 and account is None


def test_a_budget_account_cant_become_an_investment(client, db, me):
    current = db.scalar(select(Account).where(Account.name == "Current"))
    page = client.get(f"/accounts/{current.id}/edit").text
    assert 'value="crypto"' not in page  # not offered
    response = client.post(
        f"/accounts/{current.id}/edit", data={"name": "Current", "kind": "pension"}
    )
    assert response.status_code == 400
    assert "Pension accounts are always tracking only" in response.text
    db.expire_all()
    assert db.get(Account, current.id).kind == "checking"


def test_a_tracking_account_can_become_crypto_and_back(client, db, me):
    _, account = add(client, db, "Wallet", "other", on_budget=False)
    url = f"/accounts/{account.id}/edit"
    data = {"name": "Wallet", "kind": "crypto", "symbol": "sol", "quantity": "12.5"}
    assert client.post(url, data=data, follow_redirects=False).status_code == 303
    db.expire_all()
    account = db.get(Account, account.id)
    assert (account.kind, account.symbol, account.quantity) == ("crypto", "SOL", Decimal("12.5"))
    assert 'value="12.5"' in client.get(url).text

    bad = client.post(url, data={**data, "quantity": "lots"})
    assert bad.status_code == 400 and "Amount held" in bad.text

    client.post(url, data={"name": "Wallet", "kind": "other", "symbol": "SOL", "quantity": "1"})
    db.expire_all()
    account = db.get(Account, account.id)
    assert (account.kind, account.symbol, account.quantity) == ("other", None, None)


# --- update value ----------------------------------------------------------------------


@pytest.fixture
def crypto(client, db, me):
    _, account = add(
        client, db, "Coinbase XRP", "crypto", opening="1000", symbol="XRP", quantity="500"
    )
    return account


def rows(db, account):
    db.expire_all()
    return db.scalars(
        select(Transaction).where(Transaction.account_id == account.id).order_by(Transaction.id)
    ).all()


def update(client, account, value, when=TODAY, quantity=None):
    data = {"value": value, "when": when.isoformat()}
    if quantity is not None:
        data["quantity"] = quantity
    return client.post(f"/accounts/{account.id}/value", data=data, follow_redirects=False)


def test_update_value_books_the_difference(client, db, me, crypto):
    before = ready(db, me)
    page = client.get(f"/accounts/{crypto.id}/value").text
    assert 'name="quantity"' in page and 'value="500"' in page

    assert update(client, crypto, "1,250.50", quantity="520").status_code == 303
    change = rows(db, crypto)[-1]
    assert (change.payee, change.amount, change.status) == (VALUE_PAYEE, 25050, CLEARED)
    assert change.category_id is None and change.date == TODAY
    assert db.get(Account, crypto.id).quantity == Decimal("520")
    assert ready(db, me) == before  # the budget never moves

    # The same value again adds nothing (a double post is harmless).
    update(client, crypto, "1250.50", quantity="520")
    assert len(rows(db, crypto)) == 2

    # A fall is a negative change.
    update(client, crypto, "900", quantity="520")
    assert rows(db, crypto)[-1].amount == -35050


def test_update_value_on_an_earlier_date_uses_that_days_balance(client, db, me, crypto):
    earlier = TODAY - timedelta(days=10)
    # The opening balance was dated today, so ten days ago the account held nothing.
    update(client, crypto, "800", when=earlier, quantity="500")
    change = rows(db, crypto)[-1]
    assert (change.date, change.amount) == (earlier, 80000)


def test_unchanged_value_still_saves_the_amount_held(client, db, me, crypto):
    update(client, crypto, "1000", quantity="0.5")
    assert len(rows(db, crypto)) == 1
    assert db.get(Account, crypto.id).quantity == Decimal("0.5")


def test_update_value_refusals(client, db, me, crypto):
    for data, message in [
        ({"value": "", "when": TODAY.isoformat()}, "Value: Enter an amount."),
        ({"value": "abc", "when": TODAY.isoformat()}, "Value: That is not a valid amount."),
        ({"value": "10", "when": "yesterday"}, "Choose a valid date."),
        ({"value": "10", "when": "1980-01-01"}, "between 1990 and 2100"),
        ({"value": "10", "when": TODAY.isoformat(), "quantity": "x"}, "Amount held"),
    ]:
        response = client.post(f"/accounts/{crypto.id}/value", data=data)
        assert response.status_code == 400, data
        assert message in response.text
    assert len(rows(db, crypto)) == 1


def test_pension_has_no_amount_field(client, db, me):
    _, pension = add(client, db, "Vanguard SIPP", "pension", opening="20000")
    page = client.get(f"/accounts/{pension.id}/value").text
    assert 'name="quantity"' not in page
    update(client, pension, "21000", quantity="99")
    db.expire_all()
    assert db.get(Account, pension.id).quantity is None
    assert rows(db, pension)[-1].amount == 100000


def test_update_value_only_on_open_tracking_accounts(client, db, me):
    current = db.scalar(select(Account).where(Account.name == "Current"))
    assert client.get(f"/accounts/{current.id}/value").status_code == 404
    assert update(client, current, "5000").status_code == 404
    _, empty = add(client, db, "Old ISA", "isa_stocks")
    client.post(f"/accounts/{empty.id}/close", data={"closed": "true"})
    assert client.get(f"/accounts/{empty.id}/value").status_code == 404
    accounts_page = client.get("/accounts").text
    assert f"/accounts/{current.id}/value" not in accounts_page


def test_update_value_is_only_for_the_owner(client, db, me, crypto):
    db.add(User(email="other@example.com", password_hash=hash_password(PASSWORD)))
    db.commit()
    client.post("/logout")
    client.post("/login", data={"email": "other@example.com", "password": PASSWORD})
    assert client.get(f"/accounts/{crypto.id}/value").status_code == 404
    assert update(client, crypto, "1").status_code == 404
    assert len(rows(db, crypto)) == 1


def test_contributions_are_transfers_that_the_budget_counts(client, db, me, crypto):
    current = db.scalar(select(Account).where(Account.name == "Current"))
    groceries = category_id(db, "Groceries")
    client.post(
        "/transactions",
        data={
            "when": TODAY.isoformat(),
            "account_id": current.id,
            "transfer_account_id": crypto.id,
            "category_id": groceries,
            "outflow": "100",
            "payee": "",
        },
    )
    legs = rows(db, crypto)
    assert legs[-1].amount == 10000
    db.expire_all()
    line = next(
        ln
        for block in build_budget(db, me.id, month_start(TODAY)).groups
        for ln in block.lines
        if ln.category.id == groceries
    )
    assert line.activity == -10000
