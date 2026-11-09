"""Setting, changing and removing a category's target (TASK-M001).

Only standard categories take targets: card payment categories already show what they
need, and the inflow category isn't an envelope. Funding targets is on the budget page
(``routers.budget``).
"""

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..budget import month_start, parse_month
from ..deps import current_user, get_db
from ..models import BY_DATE, TARGET_KINDS, Category, Target, User
from ..money import parse_money, plain_money
from ..templating import render
from .categories import _editable_category

router = APIRouter()

NO_MONTH = date.min  # parse_month's answer for a missing or bad "by" month

KIND_LABELS = {
    "monthly": "Assign an amount every month",
    "balance": "Have a balance",
    "by_date": "Have a balance by a month",
}


def _month(value: str | None) -> date:
    return parse_month(value, month_start(date.today()))


def _target(db: Session, category: Category) -> Target | None:
    return db.scalar(select(Target).where(Target.category_id == category.id))


def _page(request, user, category, month, values, error=None, status=200, existing=None):
    context = {
        "user": user,
        "active": "budget",
        "category": category,
        "month_key": f"{month:%Y-%m}",
        "kinds": KIND_LABELS,
        "v": values,
        "existing": existing,
        "error": error,
    }
    return render(request, "target.html", context, status_code=status)


def _back(month: date) -> RedirectResponse:
    return RedirectResponse(f"/budget?month={month:%Y-%m}", status_code=303)


@router.get("/categories/{category_id}/target", response_class=HTMLResponse)
def target_form(
    request: Request,
    category_id: int,
    month: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    selected = _month(month)
    target = _target(db, category)
    values = {"kind": "monthly", "amount": "", "by": ""}
    if target is not None:
        values = {
            "kind": target.kind,
            "amount": plain_money(target.amount),
            "by": f"{target.month:%Y-%m}" if target.month else "",
        }
    return _page(request, user, category, selected, values, existing=target)


@router.post("/categories/{category_id}/target")
def save_target(
    request: Request,
    category_id: int,
    month: str = Form(""),
    kind: str = Form(...),
    amount: str = Form(""),
    by: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    selected = _month(month)
    target = _target(db, category)
    values = {"kind": kind, "amount": amount, "by": by}

    error = None
    by_month = parse_month(by, NO_MONTH) if kind == BY_DATE else None
    if by_month == NO_MONTH:
        by_month = None
    try:
        minor = parse_money(amount)
    except ValueError as exc:
        error, minor = str(exc), 0
    if kind not in TARGET_KINDS:
        error = "Choose a kind of target."
    elif error is None and minor <= 0:
        error = "The target amount must be more than zero."
    elif kind == BY_DATE and by_month is None:
        error = "Choose the month to reach the balance by."
    if error:
        return _page(request, user, category, selected, values, error, 400, target)

    if target is None:
        target = Target(user_id=user.id, category_id=category.id)
        db.add(target)
    target.kind, target.amount, target.month = kind, minor, by_month
    db.commit()
    return _back(selected)


@router.post("/categories/{category_id}/target/delete")
def delete_target(
    category_id: int,
    month: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    target = _target(db, category)
    if target is not None:
        db.delete(target)
        db.commit()
    return _back(_month(month))
