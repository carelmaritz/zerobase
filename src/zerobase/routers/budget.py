from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget import add_months, build_budget, month_start, parse_month
from ..deps import current_user, get_db, owned_category
from ..models import Assignment, Category, CategoryGroup, User
from ..money import parse_money
from ..templating import render

router = APIRouter()

MAX_NAME_LENGTH = 60


def _month_param(value: str | None) -> date:
    return parse_month(value, month_start(date.today()))


def _back(month: date) -> RedirectResponse:
    return RedirectResponse(f"/budget?month={month:%Y-%m}", status_code=303)


@router.get("/")
def home():
    return RedirectResponse("/budget", status_code=303)


def _page(
    request: Request,
    db: Session,
    user: User,
    selected: date,
    error: str | None = None,
    status: int = 200,
):
    context = {
        "user": user,
        "active": "budget",
        "view": build_budget(db, user.id, selected),
        "month_key": f"{selected:%Y-%m}",
        "month_label": f"{selected:%B %Y}",
        "prev_month": f"{add_months(selected, -1):%Y-%m}",
        "next_month": f"{add_months(selected, 1):%Y-%m}",
        "error": error,
    }
    return render(request, "budget.html", context, status_code=status)


@router.get("/budget", response_class=HTMLResponse)
def budget_page(
    request: Request,
    month: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return _page(request, db, user, _month_param(month))


@router.post("/budget/assign")
def assign(
    request: Request,
    category_id: int = Form(...),
    month: str = Form(...),
    amount: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = owned_category(db, user, category_id)
    if category.is_inflow:  # Ready to Assign is the source of assignments, not an envelope
        raise HTTPException(status_code=404, detail="Category not found")
    selected = _month_param(month)

    error = None
    try:
        minor = parse_money(amount) if amount.strip() else 0
    except ValueError as exc:
        error, minor = str(exc), None

    if minor is not None:
        existing = db.scalar(
            select(Assignment).where(
                Assignment.category_id == category.id, Assignment.month == selected
            )
        )
        if existing and minor == 0:
            db.delete(existing)
        elif existing:
            existing.amount = minor
        elif minor != 0:
            db.add(
                Assignment(user_id=user.id, category_id=category.id, month=selected, amount=minor)
            )
        db.commit()

    if request.headers.get("hx-request"):
        # Only the numbers change; the inputs stay put so tabbing between rows keeps focus.
        context = {"view": build_budget(db, user.id, selected), "error": error}
        return render(request, "_budget_oob.html", context)
    if error:
        return _page(request, db, user, selected, error, 400)
    return _back(selected)


def _clean_name(name: str) -> str | None:
    name = name.strip()
    return name if 0 < len(name) <= MAX_NAME_LENGTH else None


@router.post("/budget/groups")
def add_group(
    month: str = Form(""),
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cleaned = _clean_name(name)
    if cleaned:
        next_order = db.scalar(
            select(func.coalesce(func.max(CategoryGroup.sort_order), -1) + 1).where(
                CategoryGroup.user_id == user.id
            )
        )
        db.add(CategoryGroup(user_id=user.id, name=cleaned, sort_order=next_order))
        db.commit()
    return _back(_month_param(month))


@router.post("/budget/categories")
def add_category(
    month: str = Form(""),
    group_id: int = Form(...),
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    group = db.get(CategoryGroup, group_id)
    if group is None or group.user_id != user.id:
        return _back(_month_param(month))
    cleaned = _clean_name(name)
    if cleaned:
        next_order = db.scalar(
            select(func.coalesce(func.max(Category.sort_order), -1) + 1).where(
                Category.user_id == user.id
            )
        )
        db.add(Category(user_id=user.id, group_id=group.id, name=cleaned, sort_order=next_order))
        db.commit()
    return _back(_month_param(month))
