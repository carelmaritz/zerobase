"""Scheduled transactions (TASK-M002): when they fall due, and entering them.

A schedule repeats every ``interval`` units (``once``, ``week``, ``month`` or ``year``).
Monthly and yearly schedules keep their original day of the month (``day``) and use the
month's last day when it is shorter: the 31st falls on the 30th, then the 28th or 29th,
then the 31st again. Worked examples are in TASKS/TASK-M002.md.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta

from sqlalchemy import func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .entry import ValidTransaction, save_transaction
from .models import BY_DATE, ScheduledTransaction, Target, Transaction

log = logging.getLogger(__name__)

ONCE, WEEK, MONTH, YEAR = "once", "week", "month", "year"
UNITS = (ONCE, WEEK, MONTH, YEAR)


def on_day(year: int, month: int, day: int) -> date:
    """``day`` in that month, or the month's last day if it has fewer days."""
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def following(unit: str, interval: int, day: int, due: date) -> date | None:
    """The occurrence after ``due``, or None for a one-off schedule."""
    if unit == ONCE:
        return None
    if unit == WEEK:
        return due + timedelta(weeks=interval)
    months = interval * (12 if unit == YEAR else 1)
    index = due.year * 12 + due.month - 1 + months
    return on_day(index // 12, index % 12 + 1, day)


def occurrences(unit: str, interval: int, day: int, due: date, until: date, limit: int):
    """Due dates from ``due`` up to and including ``until``, at most ``limit`` of them."""
    found: list[date] = []
    current: date | None = due
    while current is not None and current <= until and len(found) < limit:
        found.append(current)
        current = following(unit, interval, day, current)
    return found


# How many occurrences of one schedule a single request enters. The rest follow on the
# next request, so a weekly schedule started years ago can't stall one page load.
CATCH_UP_LIMIT = 100


def is_paused(schedule: ScheduledTransaction) -> bool:
    """A schedule on a closed account (either side of a transfer) waits; nothing is entered."""
    accounts = (schedule.account, schedule.transfer_account)
    return any(account is not None and account.closed for account in accounts)


def enter(db: Session, schedule: ScheduledTransaction, due: date, on: date) -> Transaction:
    """Enter the occurrence due on ``due`` as a transaction dated ``on``. Doesn't advance."""
    valid = ValidTransaction(
        account_id=schedule.account_id,
        category_id=schedule.category_id,
        date=on,
        payee=schedule.payee,
        memo=schedule.memo,
        amount=schedule.amount,
        transfer_account_id=schedule.transfer_account_id,
        transfer_category_id=schedule.transfer_category_id,
    )
    transaction = Transaction(user_id=schedule.user_id, schedule_id=schedule.id, scheduled_for=due)
    db.add(transaction)
    save_transaction(db, schedule.user_id, valid, transaction)
    return transaction


def advance(db: Session, schedule: ScheduledTransaction) -> None:
    """Move past the next occurrence. A one-off schedule is done, so it's deleted."""
    following_due = following(schedule.unit, schedule.interval, schedule.day, schedule.next_due)
    if following_due is None:
        delete_schedule(db, schedule)
    else:
        schedule.next_due = following_due


def delete_schedule(db: Session, schedule: ScheduledTransaction) -> None:
    """Delete a schedule; what it entered stays, as ordinary transactions. Flushes."""
    # SQLite doesn't enforce the SET NULL, and a reused ID would then clash.
    db.execute(
        update(Transaction)
        .where(Transaction.schedule_id == schedule.id)
        .values(schedule_id=None)
        .execution_options(synchronize_session="fetch")
    )
    db.delete(schedule)
    db.flush()


def enter_due(db: Session, user_id: int, today: date) -> int:
    """Enter every occurrence due on or before ``today``. Returns how many were entered.

    Each schedule is locked and entered in its own savepoint. If another request got there
    first, the unique (schedule, due date) key refuses the rows and that schedule is left
    to it. The caller commits.
    """
    earliest = db.scalar(
        select(func.min(ScheduledTransaction.next_due)).where(
            ScheduledTransaction.user_id == user_id
        )
    )
    if earliest is None or earliest > today:
        return 0
    due_ids = db.scalars(
        select(ScheduledTransaction.id)
        .where(ScheduledTransaction.user_id == user_id, ScheduledTransaction.next_due <= today)
        .order_by(ScheduledTransaction.next_due, ScheduledTransaction.id)
    ).all()
    entered = 0
    for schedule_id in due_ids:
        try:
            with db.begin_nested():
                entered += _enter_one(db, schedule_id, today)
        except IntegrityError:  # another request entered it first
            continue
        except Exception:  # one bad schedule mustn't stop every page from loading
            log.exception("Couldn't enter scheduled transaction %s", schedule_id)
    return entered


def _enter_one(db: Session, schedule_id: int, today: date) -> int:
    schedule = db.scalar(
        select(ScheduledTransaction)
        .where(ScheduledTransaction.id == schedule_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if schedule is None or schedule.next_due > today or is_paused(schedule):
        return 0
    dates = occurrences(
        schedule.unit, schedule.interval, schedule.day, schedule.next_due, today, CATCH_UP_LIMIT
    )
    # Dates already entered (the next date was edited back past them) are passed over:
    # otherwise the unique key would refuse them on every request and the schedule would
    # never move on. The key then only catches two requests entering at once.
    done = set(
        db.scalars(
            select(Transaction.scheduled_for).where(
                Transaction.schedule_id == schedule.id, Transaction.scheduled_for.in_(dates)
            )
        )
    )
    entered = 0
    for due in dates:
        if due not in done:
            enter(db, schedule, due, due)
            entered += 1
        advance(db, schedule)
        if inspect(schedule).deleted:
            break
    db.flush()
    return entered


def describe(schedule: ScheduledTransaction) -> str:
    """How often, in words: "Once", "Every month", "Every 2 weeks"..."""
    if schedule.unit == ONCE:
        return "Once"
    if schedule.interval == 1:
        return f"Every {schedule.unit}"
    return f"Every {schedule.interval} {schedule.unit}s"


def upcoming(
    db: Session, user_id: int, today: date, days: int = 30, account_id: int | None = None
) -> list[tuple[date, ScheduledTransaction]]:
    """Occurrences due from now until ``days`` ahead, soonest first, paused ones included.

    With ``account_id``, only schedules on that account (either side of a transfer).
    """
    query = select(ScheduledTransaction).where(ScheduledTransaction.user_id == user_id)
    if account_id is not None:
        query = query.where(
            (ScheduledTransaction.account_id == account_id)
            | (ScheduledTransaction.transfer_account_id == account_id)
        )
    until = today + timedelta(days=days)
    found = [
        (due, schedule)
        for schedule in db.scalars(query)
        for due in occurrences(
            schedule.unit, schedule.interval, schedule.day, schedule.next_due, until, days + 1
        )
    ]
    return sorted(found, key=lambda pair: (pair[0], pair[1].id))


def budget_leg(schedule: ScheduledTransaction) -> tuple[int | None, int]:
    """The category on the budget side, and the amount there (negative: money out)."""
    if schedule.category_id is not None:
        return schedule.category_id, schedule.amount
    return schedule.transfer_category_id, -schedule.amount


def can_save_up(schedule: ScheduledTransaction) -> bool:
    """Only a yearly outflow with a category can set a yearly target (TASK-M002)."""
    category_id, amount = budget_leg(schedule)
    return (
        schedule.unit == YEAR and schedule.interval == 1 and category_id is not None and amount < 0
    )


def apply_save_up(db: Session, schedule: ScheduledTransaction) -> None:
    """Set the budget-leg category's target to save up for this yearly bill.

    By-month, repeating, for the bill's amount, in the month it's next due. It replaces
    any target the category had. Flushes.
    """
    category_id, amount = budget_leg(schedule)
    assert category_id is not None and can_save_up(schedule)
    target = db.scalar(select(Target).where(Target.category_id == category_id))
    if target is None:
        target = Target(user_id=schedule.user_id, category_id=category_id)
        db.add(target)
    target.kind, target.amount, target.repeats = BY_DATE, -amount, True
    target.month = schedule.next_due.replace(day=1)
    db.flush()
