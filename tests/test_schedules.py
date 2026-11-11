"""Scheduled transactions (TASK-M002): entering, catch-up, pausing, and the web routes.

Recurrence on plain dates is in test_schedule_dates.py.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from test_web import THIS_MONTH, category_id, register

from zerobase.budget import build_budget, category_in_use, merge_category, month_start
from zerobase.models import (
    BY_DATE,
    UNCLEARED,
    Account,
    Category,
    CategoryGroup,
    ScheduledTransaction,
    Target,
    Transaction,
    User,
)
from zerobase.schedules import CATCH_UP_LIMIT, MONTH, ONCE, WEEK, YEAR, enter_due

TODAY = date.today()


@pytest.fixture
def setup(client, db):
    """A registered user with £1,000 in Current (a budget account) and a Savings account."""
    register(client)
    client.post("/accounts", data={"name": "Current", "on_budget": "1", "opening_balance": "1000"})
    client.post("/accounts", data={"name": "Savings", "on_budget": "1", "opening_balance": "0"})
    user = db.scalar(select(User))
    current = db.scalar(select(Account.id).where(Account.name == "Current"))
    savings = db.scalar(select(Account.id).where(Account.name == "Savings"))
    return {"user": user, "current": current, "savings": savings}


def schedule(db, w, *, next_due, unit=MONTH, interval=1, amount=-50_00, **extra):
    row = ScheduledTransaction(
        user_id=w["user"].id,
        account_id=extra.pop("account_id", w["current"]),
        payee=extra.pop("payee", "Rent"),
        memo="",
        amount=amount,
        unit=unit,
        interval=interval,
        day=extra.pop("day", next_due.day),
        next_due=next_due,
        **extra,
    )
    db.add(row)
    db.commit()
    return row


def entered(db, schedule_id=None):
    db.expire_all()
    query = select(Transaction).where(Transaction.payee.in_(["Rent", "Dropbox", "Move"]))
    if schedule_id is not None:
        query = query.where(Transaction.schedule_id == schedule_id)
    return db.scalars(query.order_by(Transaction.date, Transaction.id)).all()


def add_form(w, **fields):
    data = {
        "account_id": w["current"],
        "when": TODAY.isoformat(),
        "payee": "Rent",
        "outflow": "50",
        "unit": "month",
        "interval": "1",
    }
    data.update(fields)
    return data


# --- Entering ---------------------------------------------------------------------------


def test_catches_up_each_missed_month_once(db, setup):
    s = schedule(db, setup, next_due=date(2026, 8, 1))
    assert enter_due(db, setup["user"].id, date(2026, 11, 10)) == 4
    db.commit()
    rows = entered(db, s.id)
    assert [t.date for t in rows] == [date(2026, m, 1) for m in (8, 9, 10, 11)]
    assert [t.scheduled_for for t in rows] == [t.date for t in rows]
    assert all(t.status == UNCLEARED and t.amount == -50_00 for t in rows)
    assert db.get(ScheduledTransaction, s.id).next_due == date(2026, 12, 1)
    assert enter_due(db, setup["user"].id, date(2026, 11, 30)) == 0  # nothing new


def test_month_end_schedule_keeps_its_day(db, setup):
    s = schedule(db, setup, next_due=date(2027, 1, 31))
    enter_due(db, setup["user"].id, date(2027, 4, 30))
    db.commit()
    assert [t.date for t in entered(db, s.id)] == [
        date(2027, 1, 31),
        date(2027, 2, 28),
        date(2027, 3, 31),
        date(2027, 4, 30),
    ]


def test_a_second_entry_for_the_same_date_is_refused(db, setup):
    # As if another request had just entered November's rent: this one backs off.
    s = schedule(db, setup, next_due=date(2026, 11, 1))
    db.add(
        Transaction(
            user_id=setup["user"].id,
            account_id=setup["current"],
            date=date(2026, 11, 1),
            amount=-50_00,
            payee="Rent",
            schedule_id=s.id,
            scheduled_for=date(2026, 11, 1),
        )
    )
    db.commit()
    assert enter_due(db, setup["user"].id, date(2026, 11, 10)) == 0
    db.commit()
    assert len(entered(db, s.id)) == 1
    with pytest.raises(IntegrityError):
        db.add(
            Transaction(
                user_id=setup["user"].id,
                account_id=setup["current"],
                date=date(2026, 11, 1),
                amount=-1,
                schedule_id=s.id,
                scheduled_for=date(2026, 11, 1),
            )
        )
        db.flush()
    db.rollback()


def test_editing_the_date_back_past_entered_rows_doesnt_get_stuck(client, db, setup):
    due1 = date(2027, 1, 15)
    s = schedule(db, setup, next_due=due1)
    client.post(f"/scheduled/{s.id}/enter")  # 15 Jan, entered today
    client.post(f"/scheduled/{s.id}/enter")  # 15 Feb
    db.expire_all()
    s = db.get(ScheduledTransaction, s.id)
    assert s.next_due == date(2027, 3, 15)
    s.next_due = due1  # edited back past both
    db.commit()
    # On 20 March, January and February are passed over and only March is entered.
    assert enter_due(db, setup["user"].id, date(2027, 3, 20)) == 1
    db.commit()
    assert sorted(t.scheduled_for for t in entered(db, s.id)) == [
        date(2027, 1, 15),
        date(2027, 2, 15),
        date(2027, 3, 15),
    ]
    assert db.get(ScheduledTransaction, s.id).next_due == date(2027, 4, 15)


def test_catch_up_is_capped_per_request(db, setup):
    s = schedule(db, setup, next_due=TODAY - timedelta(weeks=150), unit=WEEK)
    assert enter_due(db, setup["user"].id, TODAY) == CATCH_UP_LIMIT
    assert enter_due(db, setup["user"].id, TODAY) == 51  # 151 weekly dates in all
    db.commit()
    assert db.get(ScheduledTransaction, s.id).next_due > TODAY


def test_one_off_is_entered_then_removed(db, setup):
    s = schedule(db, setup, next_due=TODAY, unit=ONCE)
    schedule_id = s.id
    assert enter_due(db, setup["user"].id, TODAY) == 1
    db.commit()
    db.expire_all()
    assert db.get(ScheduledTransaction, schedule_id) is None
    (row,) = entered(db)
    assert row.schedule_id is None and row.date == TODAY


def test_closed_account_pauses_the_schedule(client, db, setup):
    client.post(f"/accounts/{setup['savings']}/close", data={"closed": "true"})
    s = schedule(db, setup, next_due=TODAY, account_id=setup["savings"])
    client.get("/budget")
    db.expire_all()
    assert entered(db) == []
    assert db.get(ScheduledTransaction, s.id).next_due == TODAY  # waiting, not skipped
    client.post(f"/accounts/{setup['savings']}/close", data={"closed": "false"})
    client.get("/budget")
    assert len(entered(db, s.id)) == 1


def test_scheduled_transfer_enters_both_legs(db, setup):
    s = schedule(
        db,
        setup,
        next_due=TODAY,
        payee="Move",
        amount=-100_00,
        transfer_account_id=setup["savings"],
    )
    enter_due(db, setup["user"].id, TODAY)
    db.commit()
    legs = entered(db)
    assert sorted(t.amount for t in legs) == [-100_00, 100_00]
    assert {t.account_id for t in legs} == {setup["current"], setup["savings"]}
    assert legs[0].transfer_id == legs[1].id and legs[1].transfer_id == legs[0].id
    assert [t.schedule_id for t in legs].count(s.id) == 1


def test_page_load_enters_due_rows_and_says_so_once(client, db, setup):
    groceries = category_id(db, "Groceries")
    schedule(db, setup, next_due=TODAY - timedelta(days=1), category_id=groceries)
    page = client.get("/budget").text
    assert "1 scheduled transaction entered." in page
    assert "scheduled transaction entered" not in client.get("/budget").text
    assert len(entered(db)) == 1


def test_future_schedules_dont_touch_the_budget(client, db, setup):
    groceries = category_id(db, "Groceries")
    before = build_budget(db, setup["user"].id, month_start(TODAY)).ready_to_assign
    schedule(db, setup, next_due=TODAY + timedelta(days=3), category_id=groceries)
    client.get("/budget")
    db.expire_all()
    after = build_budget(db, setup["user"].id, month_start(TODAY))
    assert after.ready_to_assign == before
    assert entered(db) == []


# --- The Scheduled page -------------------------------------------------------------------


def test_add_list_edit_and_delete(client, db, setup):
    first = TODAY + timedelta(days=5)
    response = client.post(
        "/scheduled", data=add_form(setup, when=first.isoformat()), follow_redirects=False
    )
    assert response.status_code == 303
    db.expire_all()
    s = db.scalar(select(ScheduledTransaction))
    assert (s.amount, s.unit, s.interval, s.next_due, s.day) == (-50_00, MONTH, 1, first, first.day)
    page = client.get("/scheduled").text
    assert "Rent" in page and "Every month" in page and "-£50.00" in page

    later = first + timedelta(days=2)
    client.post(
        f"/scheduled/{s.id}/edit",
        data=add_form(
            setup, when=later.isoformat(), outflow="", inflow="10", unit="week", interval="2"
        ),
    )
    db.expire_all()
    s = db.get(ScheduledTransaction, s.id)
    assert (s.amount, s.unit, s.interval, s.next_due) == (10_00, WEEK, 2, later)
    assert "Every 2 weeks" in client.get("/scheduled").text

    client.post(f"/scheduled/{s.id}/delete")
    db.expire_all()
    assert db.scalar(select(ScheduledTransaction)) is None


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"unit": "fortnight"}, "Choose how often"),
        ({"interval": "0"}, "Repeat every 1 to 99"),
        ({"interval": "abc"}, "Repeat every 1 to 99"),
        ({"outflow": ""}, "Enter either an outflow or an inflow"),
        ({"when": "2026-02-30"}, "valid date"),
        ({"save_up": "1"}, "Saving up only works for a yearly bill"),
        ({"save_up": "1", "unit": "year", "outflow": "", "inflow": "5"}, "Saving up only"),
    ],
)
def test_bad_schedules_are_refused(client, db, setup, fields, message):
    response = client.post("/scheduled", data=add_form(setup, **fields))
    assert response.status_code == 400 and message in response.text
    db.expire_all()
    assert db.scalar(select(ScheduledTransaction)) is None


def test_a_closed_account_cant_be_scheduled(client, db, setup):
    client.post(f"/accounts/{setup['savings']}/close", data={"closed": "true"})
    response = client.post("/scheduled", data=add_form(setup, account_id=setup["savings"]))
    assert response.status_code == 400 and "is closed" in response.text


def test_enter_now_dates_it_today_and_moves_on(client, db, setup):
    due = TODAY + timedelta(days=10)
    s = schedule(db, setup, next_due=due)
    client.post(f"/scheduled/{s.id}/enter")
    client.post(f"/scheduled/{s.id}/enter")  # the next one too
    rows = entered(db, s.id)
    assert [t.date for t in rows] == [TODAY, TODAY]
    assert rows[0].scheduled_for == due
    assert db.get(ScheduledTransaction, s.id).next_due > rows[1].scheduled_for


def test_enter_now_refused_while_paused(client, db, setup):
    s = schedule(db, setup, next_due=TODAY + timedelta(days=3), account_id=setup["savings"])
    client.post(f"/accounts/{setup['savings']}/close", data={"closed": "true"})
    response = client.post(f"/scheduled/{s.id}/enter")
    assert response.status_code == 400 and "paused" in response.text
    assert entered(db) == []


def test_skip_next_moves_on_without_entering(client, db, setup):
    due = TODAY + timedelta(days=3)
    s = schedule(db, setup, next_due=due, unit=WEEK)
    client.post(f"/scheduled/{s.id}/skip")
    db.expire_all()
    assert db.get(ScheduledTransaction, s.id).next_due == due + timedelta(weeks=1)
    once = schedule(db, setup, next_due=due, unit=ONCE)
    once_id = once.id
    client.post(f"/scheduled/{once_id}/skip")
    db.expire_all()
    assert db.get(ScheduledTransaction, once_id) is None
    assert entered(db) == []


def test_deleting_a_schedule_keeps_what_it_entered(client, db, setup):
    s = schedule(db, setup, next_due=TODAY - timedelta(days=1))
    client.get("/budget")
    client.post(f"/scheduled/{s.id}/delete")
    (row,) = entered(db)
    assert row.schedule_id is None


def test_upcoming_on_the_transactions_page(client, db, setup):
    schedule(db, setup, next_due=TODAY + timedelta(days=1), unit=WEEK, payee="Rent")
    page = client.get("/transactions").text
    assert "Upcoming in the next 30 days (5)" in page  # days 1, 8, 15, 22 and 29
    filtered = client.get(f"/transactions?account_id={setup['savings']}").text
    assert "Upcoming in the next" not in filtered


def test_other_users_schedules_are_off_limits(client, db, setup):
    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.flush()
    account = Account(user_id=other.id, name="Theirs")
    db.add(account)
    db.flush()
    theirs = ScheduledTransaction(
        user_id=other.id,
        account_id=account.id,
        payee="Secret",
        memo="",
        amount=-1,
        unit=MONTH,
        interval=1,
        day=1,
        next_due=TODAY + timedelta(days=5),
    )
    db.add(theirs)
    db.commit()
    theirs_id = theirs.id
    for path in ("edit", "delete", "enter", "skip"):
        assert (
            client.post(f"/scheduled/{theirs_id}/{path}", data=add_form(setup)).status_code == 404
        )
    assert client.get(f"/scheduled/{theirs_id}/edit").status_code == 404
    assert "Secret" not in client.get("/scheduled").text
    # Nor can a schedule be put on their account.
    response = client.post("/scheduled", data=add_form(setup, account_id=account.id))
    assert response.status_code == 404


# --- Categories and accounts --------------------------------------------------------------


def test_a_scheduled_category_is_in_use_and_moves_on_merge(db, setup):
    dining, groceries = category_id(db, "Dining out"), category_id(db, "Groceries")
    s = schedule(db, setup, next_due=TODAY + timedelta(days=5), category_id=dining)
    assert category_in_use(db, db.get(Category, dining))
    merge_category(db, db.get(Category, dining), db.get(Category, groceries))
    db.commit()
    assert db.get(ScheduledTransaction, s.id).category_id == groceries


def test_deleting_an_account_deletes_its_schedules(client, db, setup):
    client.post("/accounts", data={"name": "Spare", "on_budget": "1", "opening_balance": "0"})
    spare = db.scalar(select(Account.id).where(Account.name == "Spare"))
    schedule(db, setup, next_due=TODAY + timedelta(days=5), account_id=spare)
    schedule(db, setup, next_due=TODAY + timedelta(days=5), transfer_account_id=spare, payee="Move")
    client.post(f"/accounts/{spare}/delete")
    db.expire_all()
    assert db.get(Account, spare) is None
    assert db.scalar(select(ScheduledTransaction)) is None


# --- Annual bills: saving up --------------------------------------------------------------


def test_yearly_bill_sets_a_repeating_target(client, db, setup):
    group = db.scalar(select(CategoryGroup.id).where(CategoryGroup.name == "Bills"))
    client.post("/budget/categories", data={"group_id": group, "name": "Dropbox"})
    dropbox = category_id(db, "Dropbox")
    renewal = date(TODAY.year + 1, 3, 3)
    fields = add_form(
        setup,
        when=renewal.isoformat(),
        payee="Dropbox",
        outflow="119.88",
        category_id=dropbox,
        unit="year",
        save_up="1",
    )
    assert client.post("/scheduled", data=fields, follow_redirects=False).status_code == 303
    db.expire_all()
    target = db.scalar(select(Target).where(Target.category_id == dropbox))
    assert (target.kind, target.amount, target.month, target.repeats) == (
        BY_DATE,
        119_88,
        date(renewal.year, 3, 1),
        True,
    )
    page = client.get(f"/budget?month={THIS_MONTH}").text
    assert "of £119.88 by Mar" in page and "(every year)" in page

    # A price rise: editing the schedule updates the target.
    s = db.scalar(select(ScheduledTransaction))
    client.post(f"/scheduled/{s.id}/edit", data={**fields, "outflow": "129.99"})
    db.expire_all()
    assert db.scalar(select(Target.amount).where(Target.category_id == dropbox)) == 129_99


def test_saving_up_replaces_the_categorys_target(client, db, setup):
    holidays = category_id(db, "Holidays")
    client.post(
        f"/categories/{holidays}/target",
        data={"kind": "monthly", "amount": "50", "month": THIS_MONTH},
    )
    fields = add_form(
        setup,
        when=date(TODAY.year + 1, 7, 1).isoformat(),
        outflow="600",
        category_id=holidays,
        unit="year",
        save_up="1",
    )
    client.post("/scheduled", data=fields)
    db.expire_all()
    (target,) = db.scalars(select(Target)).all()
    assert (target.kind, target.amount, target.repeats) == (BY_DATE, 600_00, True)


def test_target_form_can_repeat_every_year(client, db, setup):
    holidays = category_id(db, "Holidays")
    data = {
        "kind": "by_date",
        "amount": "120",
        "by_month": "3",
        "by_year": str(TODAY.year + 1),
        "repeats": "1",
        "month": THIS_MONTH,
    }
    client.post(f"/categories/{holidays}/target", data=data)
    db.expire_all()
    assert db.scalar(select(Target.repeats))
    assert 'name="repeats" value="1" checked' in client.get(f"/categories/{holidays}/target").text
    # Repeating only applies to by-month targets.
    client.post(f"/categories/{holidays}/target", data={**data, "kind": "balance"})
    db.expire_all()
    assert db.scalar(select(Target.repeats)) is False


def test_yearly_and_monthly_schedules_enter_on_time(db, setup):
    year_s = schedule(db, setup, next_due=date(2025, 3, 3), unit=YEAR, payee="Dropbox")
    enter_due(db, setup["user"].id, date(2027, 3, 2))
    db.commit()
    assert [t.date for t in entered(db, year_s.id)] == [date(2025, 3, 3), date(2026, 3, 3)]


def test_two_requests_at_once_enter_it_once(app, db, setup):
    """PostgreSQL only: the second request waits on the schedule's row lock, then backs off."""
    if db.bind.dialect.name != "postgresql":
        pytest.skip("needs real concurrent connections")
    import threading

    s = schedule(db, setup, next_due=TODAY)
    user_id, results = setup["user"].id, {}
    first = app.state.session_factory()
    assert enter_due(first, user_id, TODAY) == 1  # holds the lock until it commits

    def second_request():
        with app.state.session_factory() as second:
            results["second"] = enter_due(second, user_id, TODAY)
            second.commit()

    thread = threading.Thread(target=second_request)
    thread.start()
    thread.join(timeout=1)
    assert thread.is_alive()  # blocked on the lock
    first.commit()
    first.close()
    thread.join(timeout=10)
    assert results["second"] == 0
    assert len(entered(db, s.id)) == 1
