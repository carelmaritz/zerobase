from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..deps import current_user, get_db, owned_account, owned_category
from ..models import Account, Category, CategoryGroup, Transaction, User
from ..money import parse_money
from ..templating import render

router = APIRouter()

PAGE_SIZE = 200


def _page(
    request: Request,
    db: Session,
    user: User,
    account_id: int | None = None,
    error: str | None = None,
    status: int = 200,
):
    query = (
        select(Transaction)
        .options(joinedload(Transaction.account), joinedload(Transaction.category))
        .where(Transaction.user_id == user.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(PAGE_SIZE)
    )
    if account_id is not None:
        query = query.where(Transaction.account_id == account_id)
    categories = db.execute(
        select(Category, CategoryGroup)
        .join(CategoryGroup, CategoryGroup.id == Category.group_id)
        .where(Category.user_id == user.id)
        .order_by(CategoryGroup.sort_order, CategoryGroup.id, Category.sort_order, Category.id)
    ).all()
    context = {
        "user": user,
        "active": "transactions",
        "transactions": db.scalars(query).unique().all(),
        "accounts": db.scalars(
            select(Account).where(Account.user_id == user.id).order_by(Account.id)
        ).all(),
        "categories": categories,
        "account_id": account_id,
        "today": date.today().isoformat(),
        "page_size": PAGE_SIZE,
        "error": error,
    }
    return render(request, "transactions.html", context, status_code=status)


@router.get("/transactions", response_class=HTMLResponse)
def transactions_page(
    request: Request,
    account_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return _page(request, db, user, account_id)


@router.post("/transactions")
def add_transaction(
    request: Request,
    account_id: int = Form(...),
    when: str = Form(...),
    payee: str = Form(""),
    memo: str = Form(""),
    category_id: str = Form(""),
    outflow: str = Form(""),
    inflow: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    def fail(message: str):
        return _page(request, db, user, error=message, status=400)

    account = owned_account(db, user, account_id)
    try:
        when_date = date.fromisoformat(when)
    except ValueError:
        return fail("Enter a valid date.")
    if not 1990 <= when_date.year <= 2100:
        return fail("The date must be between 1990 and 2100.")

    if bool(outflow.strip()) == bool(inflow.strip()):
        return fail("Enter either an outflow or an inflow amount.")
    try:
        amount = parse_money(inflow) if inflow.strip() else -parse_money(outflow)
    except ValueError as exc:
        return fail(str(exc))
    if amount == 0:
        return fail("The amount cannot be zero.")

    category = None
    if category_id.strip() and account.on_budget:  # tracking accounts never touch envelopes
        try:
            category = owned_category(db, user, int(category_id))
        except ValueError:
            return fail("Choose a valid category.")

    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            category_id=category.id if category else None,
            date=when_date,
            payee=payee.strip()[:100],
            memo=memo.strip()[:255],
            amount=amount,
        )
    )
    db.commit()
    return RedirectResponse("/transactions", status_code=303)


@router.post("/transactions/{transaction_id}/delete")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    transaction = db.get(Transaction, transaction_id)
    if transaction is not None and transaction.user_id == user.id:
        db.delete(transaction)
        db.commit()
    return RedirectResponse("/transactions", status_code=303)


@router.post("/transactions/{transaction_id}/category")
def set_category(
    request: Request,
    transaction_id: int,
    category_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    transaction = db.get(Transaction, transaction_id)
    if transaction is None or transaction.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    new_category_id = None
    if category_id.strip():
        try:
            new_category_id = owned_category(db, user, int(category_id)).id
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid category") from None
    if not transaction.account.on_budget:
        new_category_id = None
    transaction.category_id = new_category_id
    db.commit()

    if request.headers.get("hx-request"):
        return Response(status_code=204)
    return RedirectResponse("/transactions", status_code=303)
