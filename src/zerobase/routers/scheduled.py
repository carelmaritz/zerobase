"""The Scheduled page: add, edit and delete scheduled transactions; enter now; skip next.

Due schedules are entered on any page load (``deps.current_user``); see ``schedules`` and
TASKS/TASK-M002.md.
"""

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..deps import current_user, get_db
from ..entry import TransactionForm, transaction_form, validate_transaction
from ..models import ScheduledTransaction, User
from ..money import plain_money
from ..schedules import (
    UNITS,
    advance,
    apply_save_up,
    can_save_up,
    delete_schedule,
    describe,
    enter,
    is_paused,
)
from ..templating import render
from .transactions import _pickers

router = APIRouter()

UNIT_LABELS = {"once": "Once", "week": "Weeks", "month": "Months", "year": "Years"}
MAX_INTERVAL = 99
SAVE_UP_ERROR = "Saving up only works for a yearly bill, every year, paid out with a category."


def _owned(db: Session, user: User, schedule_id: int) -> ScheduledTransaction:
    schedule = db.get(ScheduledTransaction, schedule_id)
    if schedule is None or schedule.user_id != user.id:
        raise HTTPException(status_code=404, detail="Scheduled transaction not found")
    return schedule


def _back() -> RedirectResponse:
    return RedirectResponse("/scheduled", status_code=303)


def _new_values() -> dict:
    return {"when": date.today().isoformat(), "unit": "month", "interval": "1", "save_up": False}


def _values_of(schedule: ScheduledTransaction) -> dict:
    amount = schedule.amount
    return {
        "account_id": schedule.account_id,
        "transfer_account_id": schedule.transfer_account_id,
        "when": schedule.next_due.isoformat(),
        "payee": schedule.payee,
        "memo": schedule.memo,
        "category_id": schedule.category_id or schedule.transfer_category_id,
        "outflow": plain_money(-amount) if amount < 0 else "",
        "inflow": plain_money(amount) if amount > 0 else "",
        "unit": schedule.unit,
        "interval": str(schedule.interval),
        "save_up": schedule.save_up,
    }


def _page(request, db, user, values=None, error=None, status=200):
    schedules = db.scalars(
        select(ScheduledTransaction)
        .where(ScheduledTransaction.user_id == user.id)
        .order_by(ScheduledTransaction.next_due, ScheduledTransaction.id)
    ).all()
    context = {
        "user": user,
        "active": "scheduled",
        "rows": [{"s": s, "every": describe(s), "paused": is_paused(s)} for s in schedules],
        **_pickers(db, user),
        "units": UNIT_LABELS,
        "values": values or _new_values(),
        "error": error,
    }
    return render(request, "scheduled.html", context, status_code=status)


def _edit_page(request, db, user, schedule, values, error=None, status=200):
    context = {
        "user": user,
        "active": "scheduled",
        "schedule": schedule,
        "paused": is_paused(schedule),
        **_pickers(db, user),
        "units": UNIT_LABELS,
        "values": values,
        "error": error,
    }
    return render(request, "scheduled_edit.html", context, status_code=status)


def _apply(
    db: Session,
    user: User,
    form: TransactionForm,
    unit: str,
    interval: str,
    save_up: str,
    schedule: ScheduledTransaction,
) -> str | None:
    """Check the form and copy it onto ``schedule``. Returns an error message, or None."""
    if unit not in UNITS:
        return "Choose how often it repeats."
    every = int(interval) if interval.strip().isdigit() else 0
    if unit != "once" and not 1 <= every <= MAX_INTERVAL:
        return f"Repeat every 1 to {MAX_INTERVAL} {UNIT_LABELS[unit].lower()}."
    valid = validate_transaction(db, user, form)
    if isinstance(valid, str):
        return valid
    schedule.account_id, schedule.transfer_account_id = valid.account_id, valid.transfer_account_id
    schedule.category_id, schedule.transfer_category_id = (
        valid.category_id,
        valid.transfer_category_id,
    )
    schedule.payee, schedule.memo, schedule.amount = valid.payee, valid.memo, valid.amount
    schedule.unit, schedule.interval = unit, max(every, 1)
    schedule.next_due, schedule.day = valid.date, valid.date.day
    schedule.save_up = save_up == "1"
    if schedule.save_up and not can_save_up(schedule):
        return SAVE_UP_ERROR
    return None


def _form_values(form: TransactionForm, unit: str, interval: str, save_up: str) -> dict:
    return {**form.values(), "unit": unit, "interval": interval, "save_up": save_up == "1"}


@router.get("/scheduled", response_class=HTMLResponse)
def scheduled_page(
    request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    return _page(request, db, user)


@router.post("/scheduled")
def add_schedule(
    request: Request,
    form: TransactionForm = Depends(transaction_form),
    unit: str = Form("month"),
    interval: str = Form("1"),
    save_up: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    schedule = ScheduledTransaction(user_id=user.id)
    error = _apply(db, user, form, unit, interval, save_up, schedule)
    if error:
        values = _form_values(form, unit, interval, save_up)
        return _page(request, db, user, values, error, 400)
    db.add(schedule)
    db.flush()
    if schedule.save_up:
        apply_save_up(db, schedule)
    db.commit()
    return _back()


@router.get("/scheduled/{schedule_id}/edit", response_class=HTMLResponse)
def edit_schedule_form(
    request: Request,
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    schedule = _owned(db, user, schedule_id)
    return _edit_page(request, db, user, schedule, _values_of(schedule))


@router.post("/scheduled/{schedule_id}/edit")
def edit_schedule(
    request: Request,
    schedule_id: int,
    form: TransactionForm = Depends(transaction_form),
    unit: str = Form("month"),
    interval: str = Form("1"),
    save_up: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    schedule = _owned(db, user, schedule_id)
    error = _apply(db, user, form, unit, interval, save_up, schedule)
    if error:
        db.rollback()  # _apply may have changed some fields before failing
        values = _form_values(form, unit, interval, save_up)
        return _edit_page(request, db, user, schedule, values, error, 400)
    if schedule.save_up:
        apply_save_up(db, schedule)
    db.commit()
    return _back()


@router.post("/scheduled/{schedule_id}/delete")
def delete_schedule_route(
    schedule_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    delete_schedule(db, _owned(db, user, schedule_id))
    db.commit()
    return _back()


@router.post("/scheduled/{schedule_id}/enter")
def enter_now(
    request: Request,
    schedule_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Enter the next occurrence today, then move the schedule on."""
    schedule = _owned(db, user, schedule_id)
    if is_paused(schedule):
        error = "This schedule is paused: its account is closed. Reopen the account first."
        return _page(request, db, user, error=error, status=400)
    try:
        enter(db, schedule, schedule.next_due, date.today())
        advance(db, schedule)
        db.commit()
    except IntegrityError:  # a second click, or another tab, entered it first
        db.rollback()
    return _back()


@router.post("/scheduled/{schedule_id}/skip")
def skip_next(schedule_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Move past the next occurrence without entering it."""
    advance(db, _owned(db, user, schedule_id))
    db.commit()
    return _back()
