"""The transactions list: keyset paging, filters, and keeping them across forms (TASK-M005)."""

import html
import re
from datetime import date, timedelta

from sqlalchemy import select
from test_web import HX, category_id, register

from zerobase.budget import add_months, build_budget, month_start
from zerobase.models import Account, Transaction, User
from zerobase.transaction_list import PAGE_SIZE, ListFilters

TODAY = date.today()


def _ids(page: str) -> list[int]:
    return [int(i) for i in re.findall(r'href="/transactions/(\d+)/edit', page)]


def _link(page: str, rel: str) -> str | None:
    match = re.search(rf'<a href="([^"]+)" rel="{rel}"', page)
    return html.unescape(match[1]) if match else None


def _setup(client, db):
    register(client)
    client.post("/accounts", data={"name": "Current", "on_budget": "1", "opening_balance": "100"})
    client.post("/accounts", data={"name": "Joint", "on_budget": "1"})
    client.post("/accounts", data={"name": "Mortgage"})
    ids = {
        name: db.scalar(select(Account.id).where(Account.name == name))
        for name in ("Current", "Joint", "Mortgage")
    }
    user_id = db.scalar(select(User.id))
    return user_id, ids


def _add(db, user_id, account_id, when, payee="", memo="", amount=-100, category=None):
    txn = Transaction(
        user_id=user_id,
        account_id=account_id,
        date=when,
        payee=payee,
        memo=memo,
        amount=amount,
        category_id=category,
    )
    db.add(txn)
    db.flush()
    return txn


def test_paging_reaches_every_transaction_once_in_both_directions(client, db):
    user_id, ids = _setup(client, db)
    start = TODAY - timedelta(days=40)
    for n in range(450):  # 15 a day: plenty of ties on the date
        _add(db, user_id, ids["Current"], start + timedelta(days=n // 15), payee=f"Shop {n}")
    db.commit()
    everything = (
        db.execute(select(Transaction.id).order_by(Transaction.date.desc(), Transaction.id.desc()))
        .scalars()
        .all()
    )
    assert len(everything) == 451  # with the starting balance

    pages, url = [], "/transactions"
    while url:
        last_url, page = url, client.get(url).text
        pages.append(_ids(page))
        url = _link(page, "next")
    assert [len(p) for p in pages] == [PAGE_SIZE] * 4 + [51]
    assert [i for p in pages for i in p] == everything
    assert _link(client.get("/transactions").text, "prev") is None

    # And back again with Newer from the last page: the same pages, in reverse.
    page = client.get(last_url).text
    back = [_ids(page)]
    while (url := _link(page, "prev")) is not None:
        page = client.get(url).text
        back.append(_ids(page))
    assert back == list(reversed(pages))


def test_newer_from_a_short_second_page_shows_the_full_first_page(client, db):
    user_id, ids = _setup(client, db)
    for n in range(PAGE_SIZE + 10):
        _add(db, user_id, ids["Current"], TODAY - timedelta(days=n), payee=f"Shop {n}")
    db.commit()
    first = client.get("/transactions").text
    second = client.get(_link(first, "next")).text
    assert len(_ids(second)) == 11 and _link(second, "next") is None
    again = client.get(_link(second, "prev")).text
    assert _ids(again) == _ids(first) and _link(again, "prev") is None


def test_each_filter_alone_and_combined(client, db):
    user_id, ids = _setup(client, db)
    groceries, transport = category_id(db, "Groceries"), category_id(db, "Transport")
    old = TODAY - timedelta(days=60)
    a = _add(db, user_id, ids["Current"], TODAY, payee="Tesco Metro", category=groceries)
    b = _add(db, user_id, ids["Current"], old, payee="TfL", memo="tesco bag", category=transport)
    c = _add(db, user_id, ids["Joint"], TODAY, payee="Sainsbury's", category=groceries)
    d = _add(db, user_id, ids["Joint"], old, payee="Shell", memo="fuel")
    db.commit()

    def shown(query: str) -> set[int]:
        return set(_ids(client.get(f"/transactions?{query}").text)) - {e.id for e in extra}

    extra = db.scalars(select(Transaction).where(Transaction.payee == "Starting balance")).all()
    since = (TODAY - timedelta(days=7)).isoformat()
    assert shown(f"account_id={ids['Joint']}") == {c.id, d.id}
    assert shown(f"category={groceries}") == {a.id, c.id}
    assert shown(f"from={since}") == {a.id, c.id}
    assert shown(f"to={old.isoformat()}") == {b.id, d.id}
    assert shown("q=TESCO") == {a.id, b.id}  # payee or memo, any case
    assert shown(f"q=tesco&account_id={ids['Current']}&from={since}") == {a.id}
    assert shown(f"category={groceries}&account_id={ids['Joint']}") == {c.id}
    assert shown("q=nothing-like-this") == set()
    assert "No transactions match these filters." in client.get("/transactions?q=zzz").text


def test_search_text_is_literal(client, db):
    user_id, ids = _setup(client, db)
    names = ["50% off", "500 club", "a_b", "axb", r"back\slash", "backslash"]
    made = {name: _add(db, user_id, ids["Current"], TODAY, payee=name).id for name in names}
    db.commit()
    for query, expected in [("50%", "50% off"), ("a_b", "a_b"), ("k\\s", r"back\slash")]:
        page = client.get("/transactions", params={"q": query}).text
        assert set(_ids(page)) == {made[expected]}, query


def test_uncategorised_filter_matches_the_budget_count(client, db):
    user_id, ids = _setup(client, db)
    current, joint, mortgage = ids["Current"], ids["Joint"], ids["Mortgage"]
    _add(db, user_id, current, TODAY, payee="Corner shop")  # counts
    _add(db, user_id, mortgage, TODAY, payee="Interest")  # tracking: never counts
    out = _add(db, user_id, current, TODAY, amount=-500)  # budget → budget: needs no category
    into = _add(db, user_id, joint, TODAY, amount=500)
    out.transfer_id, into.transfer_id = into.id, out.id
    pay = _add(db, user_id, current, TODAY, amount=-700)  # budget → tracking: counts
    paid = _add(db, user_id, mortgage, TODAY, amount=700)
    pay.transfer_id, paid.transfer_id = paid.id, pay.id
    _add(db, user_id, current, add_months(month_start(TODAY), 1), payee="Next month")
    db.commit()

    view = build_budget(db, user_id, month_start(TODAY))
    budget_page = client.get("/budget").text
    link = html.unescape(re.search(r'<a href="([^"]+)">Categorise', budget_page)[1])
    assert link.startswith("/transactions?category=none&to=")
    listed = _ids(client.get(link).text)
    assert len(listed) == view.uncategorised_count == 2
    assert "Next month" not in client.get(link).text


def test_forms_return_to_the_same_filtered_page(client, db):
    user_id, ids = _setup(client, db)
    groceries = category_id(db, "Groceries")
    txn = _add(db, user_id, ids["Current"], TODAY, payee="Tesco", amount=-2550)
    db.commit()
    back = f"account_id={ids['Current']}&q=Tesco&before={TODAY.isoformat()}%3A99999"
    expected = f"/transactions?{back}"

    page = client.get(f"/transactions?{back}").text
    assert f'name="back" value="{html.escape(back)}"' in page

    added = client.post(
        "/transactions",
        data={
            "account_id": ids["Current"],
            "when": TODAY.isoformat(),
            "payee": "Tesco",
            "outflow": "1",
            "back": back,
        },
        follow_redirects=False,
    )
    assert added.headers["location"] == expected

    refused = client.post(
        "/transactions",
        data={"account_id": ids["Current"], "when": "nope", "outflow": "1", "back": back},
    )
    assert refused.status_code == 400
    assert 'name="q" value="Tesco"' in refused.text  # the filtered list, shown again

    saved = client.post(
        f"/transactions/{txn.id}/category",
        data={"category_id": groceries, "back": back},
        follow_redirects=False,
    )
    assert saved.headers["location"] == expected
    assert (
        client.post(
            f"/transactions/{txn.id}/category", data={"category_id": "", "back": back}, headers=HX
        ).status_code
        == 204
    )

    deleted = client.post(
        f"/transactions/{txn.id}/delete", data={"back": back}, follow_redirects=False
    )
    assert deleted.headers["location"] == expected


def test_back_can_only_lead_to_the_transactions_list(client, db):
    _setup(client, db)
    for evil in ["//evil.example", "https://evil.example/", "\r\nLocation: x", "q=a&next=//x"]:
        response = client.post(
            "/transactions/999999/delete", data={"back": evil}, follow_redirects=False
        )
        assert response.headers["location"].startswith("/transactions")
        assert "evil" not in response.headers["location"]
        assert "next" not in response.headers["location"]


def test_bad_parameters_are_ignored(client, db):
    _setup(client, db)
    page = client.get(
        "/transactions?account_id=abc&category=x&from=nope&to=2026-13-01&before=junk&after=1:2"
    )
    assert page.status_code == 200 and "Starting balance" in page.text
    assert ListFilters.from_params({"account_id": "abc", "category": "x"}) == ListFilters()


def test_other_users_rows_never_show(client, db):
    user_id, ids = _setup(client, db)
    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.flush()
    theirs = Account(user_id=other.id, name="Theirs", on_budget=True)
    db.add(theirs)
    db.flush()
    _add(db, other.id, theirs.id, TODAY, payee="Their secret")
    db.commit()
    for query in (f"account_id={theirs.id}", "q=secret", "category=none"):
        assert "Their secret" not in client.get(f"/transactions?{query}").text
