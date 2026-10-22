from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..budget import inflow_category
from ..deps import current_user, get_db, owned_account, owned_category, owned_transaction
from ..models import Account, Category, CategoryGroup, Transaction, User
from ..money import parse_money, plain_money
from ..templating import render

router = APIRouter()

PAGE_SIZE = 200


def _pickers(db: Session, user: User) -> dict:
    """Accounts and categories for the transaction form's drop-downs."""
    categories = db.execute(
        select(Category, CategoryGroup)
        .join(CategoryGroup, CategoryGroup.id == Category.group_id)
        .where(Category.user_id == user.id)
        .order_by(CategoryGroup.sort_order, CategoryGroup.id, Category.sort_order, Category.id)
    ).all()
    inflow = inflow_category(db, user.id)
    db.commit()  # in case it had to be created, so the picker never offers a phantom ID
    accounts = db.scalars(
        select(Account).where(Account.user_id == user.id).order_by(Account.id)
    ).all()
    return {"accounts": accounts, "categories": categories, "inflow": inflow}


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
    context = {
        "user": user,
        "active": "transactions",
        "transactions": db.scalars(query).unique().all(),
        **_pickers(db, user),
        "account_id": account_id,
        "values": {"account_id": account_id, "when": date.today().isoformat()},
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


@dataclass
class TransactionForm:
    """The raw fields of the add and edit forms, as submitted."""

    account_id: int
    when: str
    payee: str = ""
    memo: str = ""
    category_id: str = ""
    outflow: str = ""
    inflow: str = ""

    def values(self) -> dict:
        """The submitted values, for re-showing the form after an error."""
        category = self.category_id.strip()
        return {**vars(self), "category_id": int(category) if category.isdigit() else None}


def _form(
    account_id: int = Form(...),
    when: str = Form(...),
    payee: str = Form(""),
    memo: str = Form(""),
    category_id: str = Form(""),
    outflow: str = Form(""),
    inflow: str = Form(""),
) -> TransactionForm:
    return TransactionForm(account_id, when, payee, memo, category_id, outflow, inflow)


@dataclass
class ValidTransaction:
    account_id: int
    category_id: int | None
    date: date
    payee: str
    memo: str
    amount: int


def _validate(db: Session, user: User, form: TransactionForm) -> ValidTransaction | str:
    """Check a submitted add or edit form. Returns the clean fields, or an error message.

    A foreign account or category ID raises a 404, as everywhere else.
    """
    account = owned_account(db, user, form.account_id)
    try:
        when_date = date.fromisoformat(form.when)
    except ValueError:
        return "Enter a valid date."
    if not 1990 <= when_date.year <= 2100:
        return "The date must be between 1990 and 2100."

    if bool(form.outflow.strip()) == bool(form.inflow.strip()):
        return "Enter either an outflow or an inflow amount."
    try:
        amount = parse_money(form.inflow) if form.inflow.strip() else -parse_money(form.outflow)
    except ValueError as exc:
        return str(exc)
    if amount == 0:
        return "The amount cannot be zero."

    category_id = None
    if form.category_id.strip() and account.on_budget:  # tracking accounts never touch envelopes
        try:
            category_id = owned_category(db, user, int(form.category_id)).id
        except ValueError:
            return "Choose a valid category."

    return ValidTransaction(
        account_id=account.id,
        category_id=category_id,
        date=when_date,
        payee=form.payee.strip()[:100],
        memo=form.memo.strip()[:255],
        amount=amount,
    )


def _list_url(account_id: int | None) -> str:
    return "/transactions" if account_id is None else f"/transactions?account_id={account_id}"


@router.post("/transactions")
def add_transaction(
    request: Request,
    form: TransactionForm = Depends(_form),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    valid = _validate(db, user, form)
    if isinstance(valid, str):
        return _page(request, db, user, error=valid, status=400)
    db.add(Transaction(user_id=user.id, **vars(valid)))
    db.commit()
    return RedirectResponse("/transactions", status_code=303)


def _edit_page(
    request: Request,
    db: Session,
    user: User,
    transaction: Transaction,
    values: dict,
    return_to: int | None,
    error: str | None = None,
    status: int = 200,
):
    context = {
        "user": user,
        "active": "transactions",
        "transaction": transaction,
        **_pickers(db, user),
        "values": values,
        "return_to": return_to,
        "back_url": _list_url(return_to),
        "error": error,
    }
    return render(request, "transaction_edit.html", context, status_code=status)


@router.get("/transactions/{transaction_id}/edit", response_class=HTMLResponse)
def edit_transaction_form(
    request: Request,
    transaction_id: int,
    return_to: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    transaction = owned_transaction(db, user, transaction_id)
    amount = transaction.amount
    values = {
        "account_id": transaction.account_id,
        "when": transaction.date.isoformat(),
        "payee": transaction.payee,
        "memo": transaction.memo,
        "category_id": transaction.category_id,
        "outflow": plain_money(-amount) if amount < 0 else "",
        "inflow": plain_money(amount) if amount > 0 else "",
    }
    return _edit_page(request, db, user, transaction, values, return_to)


@router.post("/transactions/{transaction_id}/edit")
def edit_transaction(
    request: Request,
    transaction_id: int,
    form: TransactionForm = Depends(_form),
    return_to: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    transaction = owned_transaction(db, user, transaction_id)
    back_to = int(return_to) if return_to.isdigit() else None
    valid = _validate(db, user, form)
    if isinstance(valid, str):
        return _edit_page(request, db, user, transaction, form.values(), back_to, valid, 400)
    for field, value in vars(valid).items():
        setattr(transaction, field, value)
    db.commit()
    return RedirectResponse(_list_url(back_to), status_code=303)


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
