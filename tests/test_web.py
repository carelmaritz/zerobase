from datetime import date

from sqlalchemy import select

from zerobase.models import Category, CategoryGroup, User
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
