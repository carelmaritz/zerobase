from datetime import date

from sqlalchemy import select

from zerobase.models import Account, Category, CategoryGroup, Transaction, User
from zerobase.security import hash_password

PASSWORD = "correct horse battery"
HX = {"HX-Request": "true"}
THIS_MONTH = f"{date.today():%Y-%m}"


def register(client, email="me@example.com", password=PASSWORD):
    return client.post(
        "/register", data={"email": email, "password": password}, follow_redirects=False
    )


def category_id(db, name, user_email="me@example.com"):
    user = db.scalar(select(User).where(User.email == user_email))
    return db.scalar(select(Category.id).where(Category.user_id == user.id, Category.name == name))


def test_pages_require_login(client):
    for path in ("/budget", "/accounts", "/transactions"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


def test_htmx_requests_get_an_hx_redirect_when_logged_out(client):
    response = client.post(
        "/budget/assign", data={"category_id": 1, "month": THIS_MONTH}, headers=HX
    )
    assert response.status_code == 204
    assert response.headers["hx-redirect"] == "/login"


def test_healthz_and_security_headers(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    headers = client.get("/login").headers
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"


def test_first_user_registers_then_registration_closes(client, db):
    response = register(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/accounts"
    assert category_id(db, "Groceries") is not None  # default categories were seeded

    client.post("/logout")
    assert register(client, "second@example.com").status_code == 403
    assert client.get("/register", follow_redirects=False).status_code == 303


def test_registration_validation(client):
    assert register(client, "not-an-email").status_code == 400
    assert register(client, "me@example.com", "short").status_code == 400


def test_login_flow_and_throttle(client):
    register(client)
    client.post("/logout")

    bad = client.post("/login", data={"email": "me@example.com", "password": "nope-nope-nope"})
    assert bad.status_code == 400
    assert "Incorrect email or password" in bad.text

    good = client.post(
        "/login", data={"email": "me@example.com", "password": PASSWORD}, follow_redirects=False
    )
    assert good.status_code == 303
    assert good.headers["location"] == "/budget"

    client.post("/logout")
    for _ in range(8):
        client.post("/login", data={"email": "x@example.com", "password": "wrong-wrong-wrong"})
    locked = client.post("/login", data={"email": "x@example.com", "password": "wrong-wrong"})
    assert locked.status_code == 429


def test_cross_site_posts_are_blocked(client):
    register(client)
    response = client.post("/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert client.get("/budget").status_code == 200  # still signed in


def test_end_to_end_budgeting(client, db):
    register(client)
    client.post(
        "/accounts",
        data={"name": "Current", "kind": "checking", "on_budget": "1", "opening_balance": "1000"},
    )
    page = client.get("/budget")
    assert "£1,000.00" in page.text  # opening balance is waiting in Ready to Assign

    groceries = category_id(db, "Groceries")
    assigned = client.post(
        "/budget/assign",
        data={"category_id": groceries, "month": THIS_MONTH, "amount": "400"},
        headers=HX,
    )
    assert assigned.status_code == 200
    assert 'id="rta"' in assigned.text and "£600.00" in assigned.text
    assert f'id="avail-{groceries}"' in assigned.text and "£400.00" in assigned.text

    account_id = client.get("/transactions").text.split('name="account_id"')[1].split('value="')[1]
    account_id = int(account_id.split('"')[0])
    added = client.post(
        "/transactions",
        data={
            "account_id": account_id,
            "when": date.today().isoformat(),
            "payee": "Tesco",
            "category_id": groceries,
            "outflow": "25.50",
        },
        follow_redirects=False,
    )
    assert added.status_code == 303

    budget = client.get(f"/budget?month={THIS_MONTH}").text
    assert "-£25.50" in budget and "£374.50" in budget
    assert "Tesco" in client.get("/transactions").text


def test_invalid_assignment_reports_an_error_without_changing_anything(client, db):
    register(client)
    groceries = category_id(db, "Groceries")
    response = client.post(
        "/budget/assign",
        data={"category_id": groceries, "month": THIS_MONTH, "amount": "lots"},
        headers=HX,
    )
    assert response.status_code == 200
    assert "not a valid amount" in response.text


def test_transaction_validation(client, db):
    register(client)
    client.post("/accounts", data={"name": "Current", "on_budget": "1"})
    account_id = 1
    base = {"account_id": account_id, "when": date.today().isoformat()}
    assert client.post("/transactions", data={**base}).status_code == 400  # no amount
    both = {**base, "outflow": "1", "inflow": "1"}
    assert client.post("/transactions", data=both).status_code == 400
    assert client.post("/transactions", data={**base, "outflow": "x"}).status_code == 400
    assert (
        client.post("/transactions", data={**base, "when": "nope", "outflow": "1"}).status_code
        == 400
    )
    assert client.post("/transactions", data={**base, "outflow": "0"}).status_code == 400


def test_other_users_data_is_off_limits(client, db):
    register(client)
    other = User(email="other@example.com", password_hash=hash_password(PASSWORD))
    db.add(other)
    db.flush()
    group = CategoryGroup(user_id=other.id, name="Private")
    db.add(group)
    db.flush()
    secret = Category(user_id=other.id, group_id=group.id, name="Secret")
    db.add(secret)
    db.commit()

    response = client.post(
        "/budget/assign", data={"category_id": secret.id, "month": THIS_MONTH, "amount": "5"}
    )
    assert response.status_code == 404
    assert "Secret" not in client.get("/budget").text


def test_income_uses_the_inflow_category(client, db):
    register(client)
    user = db.scalar(select(User).where(User.email == "me@example.com"))
    inflow = db.scalar(
        select(Category).where(Category.user_id == user.id, Category.kind == "inflow")
    )
    assert inflow is not None and inflow.group_id is None

    client.post("/accounts", data={"name": "Current", "on_budget": "1", "opening_balance": "100"})
    client.post("/accounts", data={"name": "Overdraft", "on_budget": "1", "opening_balance": "-30"})
    client.post("/accounts", data={"name": "Mortgage", "opening_balance": "-5000"})
    starts = db.scalars(select(Transaction).where(Transaction.user_id == user.id)).all()
    by_amount = {t.amount: t.category_id for t in starts}
    assert by_amount == {10_000: inflow.id, -3_000: inflow.id, -500_000: None}

    page = client.get("/transactions").text
    assert f'<option value="{inflow.id}">Inflow: Ready to Assign</option>' in page
    account_id = db.scalar(select(Account.id).where(Account.name == "Current"))
    base = {"account_id": account_id, "when": date.today().isoformat()}
    client.post("/transactions", data={**base, "category_id": inflow.id, "inflow": "50"})
    client.post("/transactions", data={**base, "inflow": "20"})  # no category: not income

    budget = client.get(f"/budget?month={THIS_MONTH}").text
    assert "£120.00" in budget  # 100 - 30 + 50
    assert "1 uncategorised transaction" in budget and "£20.00 in" in budget
    assert "Inflow" not in budget  # never shown as an envelope

    refused = client.post(
        "/budget/assign", data={"category_id": inflow.id, "month": THIS_MONTH, "amount": "5"}
    )
    assert refused.status_code == 404


def _edit_setup(client, db):
    """A user with a budget account, a tracking account and one Tesco transaction."""
    register(client)
    client.post("/accounts", data={"name": "Current", "on_budget": "1", "opening_balance": "1000"})
    client.post("/accounts", data={"name": "Mortgage"})
    current = db.scalar(select(Account.id).where(Account.name == "Current"))
    mortgage = db.scalar(select(Account.id).where(Account.name == "Mortgage"))
    groceries = category_id(db, "Groceries")
    client.post(
        "/transactions",
        data={
            "account_id": current,
            "when": date.today().isoformat(),
            "payee": "Tesco",
            "category_id": groceries,
            "outflow": "25.50",
        },
    )
    txn = db.scalar(select(Transaction).where(Transaction.payee == "Tesco"))
    return {"current": current, "mortgage": mortgage, "groceries": groceries, "txn": txn}


def _edit(client, s, **changes):
    t = s["txn"]
    data = {
        "account_id": t.account_id,
        "when": t.date.isoformat(),
        "payee": t.payee,
        "memo": t.memo,
        "category_id": t.category_id or "",
        "outflow": "25.50",
        "inflow": "",
        **changes,
    }
    return client.post(f"/transactions/{t.id}/edit", data=data, follow_redirects=False)


def test_edit_form_shows_the_transaction(client, db):
    s = _edit_setup(client, db)
    page = client.get(f"/transactions/{s['txn'].id}/edit").text
    assert 'value="Tesco"' in page and 'value="25.50"' in page
    assert f'<option value="{s["groceries"]}" selected>Groceries</option>' in page
    assert f'href="/transactions/{s["txn"].id}/edit"' in client.get("/transactions").text


def test_edit_every_field_updates_balances_and_budget(client, db):
    s = _edit_setup(client, db)
    dining = category_id(db, "Dining out")
    response = _edit(
        client,
        s,
        payee="Pizza",
        memo="birthday",
        category_id=dining,
        outflow="40",
        when="2026-09-15",
    )
    assert response.status_code == 303 and response.headers["location"] == "/transactions"

    db.refresh(s["txn"])
    t = s["txn"]
    assert (t.payee, t.memo, t.category_id, t.amount, t.date) == (
        "Pizza",
        "birthday",
        dining,
        -4_000,
        date(2026, 9, 15),
    )
    assert "£960.00" in client.get("/accounts").text  # 1,000 - 40
    september = client.get("/budget?month=2026-09").text
    assert f'id="act-{dining}" class="num neg">-£40.00' in september
    assert f'id="act-{s["groceries"]}" class="num zero">£0.00' in september


def test_edit_into_the_inflow_category_makes_it_income(client, db):
    s = _edit_setup(client, db)
    inflow = db.scalar(select(Category.id).where(Category.kind == "inflow"))
    _edit(client, s, category_id=inflow, outflow="", inflow="25.50")
    assert "£1,025.50" in client.get(f"/budget?month={THIS_MONTH}").text


def test_moving_to_a_tracking_account_clears_the_category(client, db):
    s = _edit_setup(client, db)
    _edit(client, s, account_id=s["mortgage"])
    db.refresh(s["txn"])
    assert (s["txn"].account_id, s["txn"].category_id) == (s["mortgage"], None)


def test_invalid_edit_reshows_the_form_and_changes_nothing(client, db):
    s = _edit_setup(client, db)
    for changes, message in [
        ({"inflow": "1"}, "either an outflow or an inflow"),
        ({"outflow": "0"}, "cannot be zero"),
        ({"when": "nope"}, "valid date"),
        ({"outflow": "abc", "payee": "Typo"}, "not a valid amount"),
    ]:
        response = _edit(client, s, **changes)
        assert response.status_code == 400 and message in response.text
    assert 'value="Typo"' in response.text and 'value="abc"' in response.text
    db.refresh(s["txn"])
    assert (s["txn"].payee, s["txn"].amount) == ("Tesco", -2_550)


def test_edit_returns_to_the_filtered_list(client, db):
    s = _edit_setup(client, db)
    page = client.get(f"/transactions?account_id={s['current']}").text
    assert f"/edit?return_to={s['current']}" in page
    form = client.get(f"/transactions/{s['txn'].id}/edit?return_to={s['current']}").text
    assert f'name="return_to" value="{s["current"]}"' in form
    response = _edit(client, s, return_to=str(s["current"]))
    assert response.headers["location"] == f"/transactions?account_id={s['current']}"


def test_other_users_transactions_and_accounts_cannot_be_edited(client, db):
    s = _edit_setup(client, db)
    other = User(email="other@example.com", password_hash=hash_password(PASSWORD))
    db.add(other)
    db.flush()
    theirs = Account(user_id=other.id, name="Theirs")
    db.add(theirs)
    db.flush()
    their_txn = Transaction(
        user_id=other.id, account_id=theirs.id, date=date.today(), payee="Secret", amount=-100
    )
    db.add(their_txn)
    db.commit()

    assert client.get(f"/transactions/{their_txn.id}/edit").status_code == 404
    data = {"account_id": theirs.id, "when": date.today().isoformat(), "outflow": "1"}
    assert client.post(f"/transactions/{their_txn.id}/edit", data=data).status_code == 404
    assert _edit(client, s, account_id=theirs.id).status_code == 404  # move into their account
    db.refresh(s["txn"])
    assert s["txn"].account_id == s["current"]
