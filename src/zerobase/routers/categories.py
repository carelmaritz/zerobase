"""Managing categories and groups: rename, reorder, move, hide and delete.

Deleting a category that has transactions or assignments merges it into another
category (``budget.merge_category``); the confirm page previews the effect on Ready to
Assign first. Only standard categories and groups are managed here: the built-in inflow
category, card payment categories and the card payments group follow their card.
"""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget import build_budget, category_in_use, merge_category, month_start
from ..deps import current_user, get_db, owned_category
from ..models import Category, CategoryGroup, User
from ..templating import render
from .budget import clean_name

router = APIRouter()

NAME_ERROR = "Names must be 1 to 60 characters."


def _back() -> RedirectResponse:
    return RedirectResponse("/categories", status_code=303)


def _editable_category(db: Session, user: User, category_id: int) -> Category:
    category = owned_category(db, user, category_id)
    if category.kind != "standard":
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def _owned_group(db: Session, user: User, group_id: int) -> CategoryGroup:
    group = db.get(CategoryGroup, group_id)
    if group is None or group.user_id != user.id or group.kind != "standard":
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def _groups(db: Session, user: User) -> list[CategoryGroup]:
    return list(
        db.scalars(
            select(CategoryGroup)
            .where(CategoryGroup.user_id == user.id, CategoryGroup.kind == "standard")
            .order_by(CategoryGroup.sort_order, CategoryGroup.id)
        )
    )


def _categories(db: Session, user: User, group_id: int | None = None) -> list[Category]:
    """Standard categories, by group then position. Hidden ones included."""
    query = (
        select(Category)
        .join(CategoryGroup, CategoryGroup.id == Category.group_id)
        .where(Category.user_id == user.id, Category.kind == "standard")
        .order_by(CategoryGroup.sort_order, CategoryGroup.id, Category.sort_order, Category.id)
    )
    if group_id is not None:
        query = query.where(Category.group_id == group_id)
    return list(db.scalars(query))


def _shift(items: list, item, direction: Literal["up", "down"]) -> None:
    """Move ``item`` one place up or down in ``items``, renumbering their sort_order."""
    index = items.index(item)
    other = index - 1 if direction == "up" else index + 1
    if 0 <= other < len(items):
        items[index], items[other] = items[other], items[index]
    for position, each in enumerate(items):
        each.sort_order = position


def _page(
    request: Request,
    db: Session,
    user: User,
    error: str | None = None,
    notice: str | None = None,
    status: int = 200,
):
    groups = _groups(db, user)
    categories = _categories(db, user)
    context = {
        "user": user,
        "active": "budget",
        "groups": [(g, [c for c in categories if c.group_id == g.id]) for g in groups],
        "error": error,
        "notice": notice,
    }
    return render(request, "categories.html", context, status_code=status)


@router.get("/categories", response_class=HTMLResponse)
def categories_page(
    request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    return _page(request, db, user)


@router.post("/categories/{category_id}/rename")
def rename_category(
    request: Request,
    category_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    cleaned = clean_name(name)
    if cleaned is None:
        return _page(request, db, user, NAME_ERROR, status=400)
    category.name = cleaned
    db.commit()
    return _back()


@router.post("/categories/{category_id}/move")
def move_category(
    category_id: int,
    direction: Literal["up", "down"] = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    _shift(_categories(db, user, category.group_id), category, direction)
    db.commit()
    return _back()


@router.post("/categories/{category_id}/group")
def change_group(
    category_id: int,
    group_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    group = _owned_group(db, user, group_id)
    if group.id != category.group_id:
        category.sort_order = db.scalar(
            select(func.coalesce(func.max(Category.sort_order), -1) + 1).where(
                Category.group_id == group.id
            )
        )
        category.group_id = group.id
        db.commit()
    return _back()


@router.post("/categories/{category_id}/hide")
def hide_category(
    request: Request,
    category_id: int,
    hidden: bool = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    category.hidden = hidden
    db.commit()
    if hidden:
        view = build_budget(db, user.id, month_start(date.today()))
        available = next(ln.available for ln in view.hidden if ln.category.id == category.id)
        if available:
            notice = {"name": category.name, "available": available}
            return _page(request, db, user, notice=notice)
    return _back()


def _delete_page(
    request: Request,
    db: Session,
    user: User,
    category: Category,
    target: Category | None = None,
    error: str | None = None,
    status: int = 200,
):
    month = month_start(date.today())
    preview = None
    if target is not None:
        before = build_budget(db, user.id, month).ready_to_assign
        after = build_budget(db, user.id, month, merge=(category.id, target.id)).ready_to_assign
        preview = {"before": before, "after": after, "month": f"{month:%B %Y}"}
    context = {
        "user": user,
        "active": "budget",
        "category": category,
        "in_use": category_in_use(db, category),
        "targets": [c for c in _categories(db, user) if c.id != category.id],
        "target": target,
        "preview": preview,
        "error": error,
    }
    return render(request, "category_delete.html", context, status_code=status)


def _target(db: Session, user: User, category: Category, target_id: str) -> Category | None:
    """The category to merge into, or None if none was chosen. Rejects unusable ones."""
    if not target_id.strip():
        return None
    try:
        target = _editable_category(db, user, int(target_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid category") from None
    if target.id == category.id:
        raise HTTPException(status_code=400, detail="Choose a different category")
    return target


@router.get("/categories/{category_id}/delete", response_class=HTMLResponse)
def delete_category_form(
    request: Request,
    category_id: int,
    target_id: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    return _delete_page(request, db, user, category, _target(db, user, category, target_id))


@router.post("/categories/{category_id}/delete")
def delete_category(
    request: Request,
    category_id: int,
    target_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    category = _editable_category(db, user, category_id)
    target = _target(db, user, category, target_id)
    if target is not None:
        merge_category(db, category, target)
    elif category_in_use(db, category):
        error = "This category has transactions or assignments. Choose where they should go."
        return _delete_page(request, db, user, category, error=error, status=400)
    else:
        db.delete(category)
    db.commit()
    return _back()


@router.post("/groups/{group_id}/rename")
def rename_group(
    request: Request,
    group_id: int,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    group = _owned_group(db, user, group_id)
    cleaned = clean_name(name)
    if cleaned is None:
        return _page(request, db, user, NAME_ERROR, status=400)
    group.name = cleaned
    db.commit()
    return _back()


@router.post("/groups/{group_id}/move")
def move_group(
    group_id: int,
    direction: Literal["up", "down"] = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    group = _owned_group(db, user, group_id)
    _shift(_groups(db, user), group, direction)
    db.commit()
    return _back()


@router.post("/groups/{group_id}/delete")
def delete_group(
    request: Request,
    group_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    group = _owned_group(db, user, group_id)
    has_categories = db.scalar(select(Category.id).where(Category.group_id == group.id).limit(1))
    if has_categories is not None:
        error = f"Move or delete the categories in {group.name} first."
        return _page(request, db, user, error, status=400)
    db.delete(group)
    db.commit()
    return _back()
