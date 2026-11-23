"""Reports: income, spending, moved, net worth (TASK-M003). Totals are worked out by hand."""

import re
import time
from datetime import date

import pytest
from sqlalchemy import select
from test_web import category_id, register

from zerobase import charts
from zerobase.models import Account, Transaction, User
from zerobase.reports import MonthRange, cash_flow, net_worth

TODAY = date(2026, 2, 20)
RANGE = MonthRange(date(2025, 12, 1), date(2026, 2, 1))  # spans a year end


@pytest.fixture
def world(client, db):
    register(client)
    user = db.scalar(select(User))

    def account(name, kind="checking", on_budget=True):
        row = Account(user_id=user.id, name=name, kind=kind, on_budget=on_budget)
        db.add(row)
        db.flush()
        return row

    accounts = {
        "current": account("Current"),
        "savings": account("Savings", "savings"),
        "pension": account("Pension", "pension", False),
        "home": account("Home", "property", False),
        "mortgage": account("Mortgage", "other", False),
    }
    from zerobase.budget import inflow_category

    cats = {
        "income": inflow_category(db, user.id).id,
        "food": category_id(db, "Groceries"),
        "rent": category_id(db, "Rent / Mortgage"),
    }

    def add(when, acc, amount, cat=None, **extra):
        row = Transaction(
            user_id=user.id,
            account_id=accounts[acc].id,
            date=date.fromisoformat(when),
            amount=amount,
            category_id=cats.get(cat),
            payee="x",
            **extra,
        )
        db.add(row)
        db.flush()
        return row

    def transfer(when, source, target, amount, cat=None, target_cat=None):
        a = add(when, source, -amount, cat)
        b = add(when, target, amount, target_cat)
        a.transfer_id, b.transfer_id = b.id, a.id
        db.flush()

    class World:
        pass

    w = World()
    w.user, w.add, w.transfer, w.accounts, w.cats = user, add, transfer, accounts, cats
    return w


def by_name(flow):
    return {c.name: c.amounts for g in flow.groups for c in g.categories}


def test_income_spending_and_refunds_over_a_year_end(db, world):
    world.add("2025-11-30", "current", 99900, "income")  # before the range
    world.add("2025-12-01", "current", 200000, "income")
    world.add("2025-12-31", "current", -5000, "food")
    world.add("2026-01-01", "current", -7000, "food")
    world.add("2026-01-15", "current", 1500, "food")  # refund
    world.add("2026-02-28", "current", -60000, "rent")
    world.add("2026-03-01", "current", -1, "rent")  # after it
    flow = cash_flow(db, world.user.id, RANGE)
    assert flow.income == [200000, 0, 0]
    assert flow.spending == [5000, 5500, 60000]
    assert flow.net == [195000, -5500, -60000]
    assert by_name(flow) == {"Groceries": [5000, 5500, 0], "Rent / Mortgage": [0, 0, 60000]}
    assert sum(g.total for g in flow.groups) == sum(flow.spending)


def test_starting_balances_and_card_starting_debt_count_nowhere(client, db):
    register(client)
    for name, kind, opening in (("C", "checking", "1000"), ("V", "credit_card", "-500")):
        data = {"name": name, "kind": kind, "on_budget": "1", "opening_balance": opening}
        client.post("/accounts", data=data)
    user = db.scalar(select(User))
    assert all(t.is_starting for t in db.scalars(select(Transaction)))
    today = date.today()
    months = MonthRange.build(None, None, today)
    flow = cash_flow(db, user.id, months)
    assert not any(flow.income) and not any(flow.spending)
    worth = net_worth(db, user.id, months, today)
    assert (worth.cash[-1], worth.debt[-1], worth.total[-1]) == (100000, -50000, 50000)


def test_editing_the_payee_keeps_the_starting_marker(client, db):
    register(client)
    data = {"name": "C", "kind": "checking", "on_budget": "1", "opening_balance": "10"}
    client.post("/accounts", data=data)
    row = db.scalar(select(Transaction))
    form = {
        "account_id": row.account_id,
        "when": row.date.isoformat(),
        "payee": "Starting odd",
        "inflow": "10",
        "category_id": row.category_id,
        "status": "cleared",
    }
    client.post(f"/transactions/{row.id}/edit", data=form)
    db.expire_all()
    row = db.scalar(select(Transaction))
    assert row.payee == "Starting odd" and row.is_starting


def test_transfers_are_not_income_or_spending(db, world):
    world.transfer("2026-01-05", "current", "savings", 10000)
    world.transfer("2026-01-06", "current", "pension", 30000, "rent")
    world.transfer("2026-02-06", "pension", "current", 12000, target_cat="income")
    flow = cash_flow(db, world.user.id, RANGE)
    assert flow.income == flow.spending == [0, 0, 0]
    assert flow.moved == [0, 30000, -12000]
    assert flow.uncategorised_count == 0


def test_uncategorised_rows_are_only_counted(db, world):
    world.add("2026-01-05", "current", 2500)
    world.add("2026-01-06", "current", -900)
    world.add("2026-01-06", "pension", 5000)  # tracking: never needs a category
    flow = cash_flow(db, world.user.id, RANGE)
    assert flow.income == flow.spending == [0, 0, 0]
    assert (flow.uncategorised_count, flow.uncategorised_in, flow.uncategorised_out) == (
        2,
        2500,
        -900,
    )


def test_net_worth_is_split_and_adds_up(db, world):
    world.add("2025-06-01", "current", 100000, "income")  # carried into the range
    world.add("2025-12-31", "home", 35000000)
    world.add("2025-12-31", "mortgage", -20000000)
    world.add("2026-01-10", "pension", 5000000)
    world.add("2026-02-01", "current", -150000, "rent")  # overdrawn: becomes debt
    world.add("2026-02-21", "current", 999999, "income")  # after today
    worth = net_worth(db, world.user.id, RANGE, TODAY)
    assert worth.cash == [100000, 100000, 0]
    assert worth.property == [35000000] * 3
    assert worth.investments == [0, 5000000, 5000000]
    assert worth.debt == [-20000000, -20000000, -20050000]
    assert worth.total == [15100000, 20100000, 19950000]


def test_other_users_are_not_counted(db, world):
    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.flush()
    world.add("2026-01-05", "current", 5000, "income")
    flow = cash_flow(db, other.id, RANGE)
    assert flow.income == [0, 0, 0] and flow.groups == []
    assert net_worth(db, other.id, RANGE, TODAY).total == [0, 0, 0]


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (None, None, (date(2025, 3, 1), date(2026, 2, 1))),
        (date(2026, 2, 1), date(2026, 1, 1), (date(2026, 1, 1), date(2026, 2, 1))),
        (date(2026, 1, 1), date(2030, 1, 1), (date(2026, 1, 1), date(2026, 2, 1))),
        (date(2031, 1, 1), date(2031, 2, 1), (date(2026, 2, 1), date(2026, 2, 1))),
        (date(1990, 1, 1), None, (date(2016, 3, 1), date(2026, 2, 1))),
    ],
)
def test_month_range(start, end, expected):
    r = MonthRange.build(start, end, TODAY)
    assert (r.start, r.end) == expected


def test_tick_steps_are_round():
    for span in (1, 99, 100, 12345, 987654321):
        step = charts.tick_step(span)
        assert str(step).rstrip("0") in {"1", "2", "5"} and step * 5 >= span / 2


def test_ranked_folds_small_categories():
    chart = charts.ranked([(f"c{i}", i) for i in range(-2, 20)])
    assert len(chart.rows) == charts.MAX_ROWS
    assert sum(r.value for r in chart.rows) == sum(range(1, 20))


def test_page_needs_login(client):
    assert client.get("/reports", follow_redirects=False).status_code == 303


def test_empty_page_and_bad_parameters(client):
    register(client)
    for query in ("", "?from_month=13&from_year=x&to_month=&to_year=0"):
        page = client.get(f"/reports{query}")
        assert page.status_code == 200
        assert "No spending in these months." in page.text


def test_page_shows_figures_without_inline_style_or_script(client, db, world):
    world.add("2026-01-05", "current", -123456, "food")
    world.add("2026-01-06", "current", -900)
    db.commit()
    page = client.get("/reports?from_month=12&from_year=2025&to_month=2&to_year=2026").text
    assert "£1,234.56" in page and "Jan 2026: Spending £1,234.56" in page
    assert "/transactions?category=none&amp;from=2025-12-01&amp;to=2026-02-28" in page
    assert " style=" not in page and not re.search(r"<script(?! src)", page)


def test_names_are_escaped(client, db, world):
    from zerobase.models import Category

    db.get(Category, world.cats["food"]).name = "<b>x</b>"
    world.add("2026-01-05", "current", -100, "food")
    db.commit()
    page = client.get("/reports?from_month=1&from_year=2026&to_month=2&to_year=2026").text
    assert "<b>x</b>" not in page and "&lt;b&gt;x" in page


def test_five_years_load_quickly(client, db, world):
    today = date.today()
    start = date(today.year - 4, 1, 1).toordinal()
    span = today.toordinal() - start
    db.add_all(
        Transaction(
            user_id=world.user.id,
            account_id=world.accounts["current"].id,
            category_id=world.cats["food" if i % 3 else "income"],
            date=date.fromordinal(start + i * span // 10_000),
            payee="x",
            amount=-100 - i % 50 if i % 3 else 500,
        )
        for i in range(10_000)
    )
    db.commit()
    url = f"/reports?from_month=1&from_year={today.year - 4}"
    client.get(url)
    began = time.perf_counter()
    assert client.get(url).status_code == 200
    took = time.perf_counter() - began
    print(f"reports page: {took * 1000:.0f} ms")
    assert took < 0.5
