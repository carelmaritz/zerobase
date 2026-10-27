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
    values: dict | None = None,
):
    query = (
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.transfer).joinedload(Transaction.account),
        )
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
        "values": values or {"account_id": account_id, "when": date.today().isoformat()},
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
    transfer_account_id: str = ""

    def values(self) -> dict:
        """The submitted values, for re-showing the form after an error."""
        return {
            **vars(self),
            "category_id": _optional_id(self.category_id),
            "transfer_account_id": _optional_id(self.transfer_account_id),
        }


def _optional_id(value: str) -> int | None:
    value = value.strip()
    return int(value) if value.isdigit() else None


def _form(
    account_id: int = Form(...),
    when: str = Form(...),
    payee: str = Form(""),
    memo: str = Form(""),
    category_id: str = Form(""),
    outflow: str = Form(""),
    inflow: str = Form(""),
    transfer_account_id: str = Form(""),
) -> TransactionForm:
    return TransactionForm(
        account_id, when, payee, memo, category_id, outflow, inflow, transfer_account_id
    )


@dataclass
class ValidTransaction:
    account_id: int
    category_id: int | None
    date: date
    payee: str
    memo: str
    amount: int
    # For a transfer: the other account, and the category of the leg there.
    transfer_account_id: int | None = None
    transfer_category_id: int | None = None


def _validate(db: Session, user: User, form: TransactionForm) -> ValidTransaction | str:
    """Check a submitted add or edit form. Returns the clean fields, or an error message.

    A foreign account or category ID raises a 404, as everywhere else. For a transfer, the
    amount is from this account's side; the other leg gets the opposite.
    """
    account = owned_account(db, user, form.account_id)
    transfer = None
    if form.transfer_account_id.strip():
        try:
            transfer = owned_account(db, user, int(form.transfer_account_id))
        except ValueError:
            return "Choose a valid account to transfer to or from."
        if transfer.id == account.id:
            return "A transfer needs two different accounts."
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
    if form.category_id.strip():
        try:
            category_id = owned_category(db, user, int(form.category_id)).id
        except ValueError:
            return "Choose a valid category."

    # Only a budget-account leg can have a category; for a transfer, only when the money
    # leaves or enters the budget, and then it must have one.
    transfer_category_id = None
    if transfer is None:
        if not account.on_budget:  # tracking accounts never touch envelopes
            category_id = None
    elif account.on_budget == transfer.on_budget:
        if category_id is not None:
            return (
                "Leave the category blank: a transfer between two budget accounts, or two "
                "tracking accounts, doesn't touch the envelopes."
            )
    elif category_id is None:
        return "Choose a category: this transfer moves money into or out of the budget."
    elif not account.on_budget:
        category_id, transfer_category_id = None, category_id

    return ValidTransaction(
        account_id=account.id,
        category_id=category_id,
        date=when_date,
        payee=form.payee.strip()[:100],
        memo=form.memo.strip()[:255],
        amount=amount,
        transfer_account_id=transfer.id if transfer else None,
        transfer_category_id=transfer_category_id,
    )


def _save(db: Session, user: User, valid: ValidTransaction, transaction: Transaction) -> None:
    """Apply checked fields to a new or existing transaction, keeping any other leg in step.

    Adding a transfer account creates the other leg; removing it deletes that leg. The
    caller commits, so both legs change together.
    """
    for field in ("account_id", "category_id", "date", "payee", "memo", "amount"):
        setattr(transaction, field, getattr(valid, field))
    other = db.get(Transaction, transaction.transfer_id) if transaction.transfer_id else None

    if valid.transfer_account_id is None:
        if other is not None:
            transaction.transfer_id = None
            db.delete(other)
        return

    if other is None:
        other = Transaction(user_id=user.id)
        db.add(other)
    other.account_id = valid.transfer_account_id
    other.category_id = valid.transfer_category_id
    other.date, other.payee, other.memo = valid.date, valid.payee, valid.memo
    other.amount = -valid.amount
    db.flush()  # both legs need IDs before they can point at each other
    transaction.transfer_id, other.transfer_id = other.id, transaction.id


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
        return _page(request, db, user, error=valid, status=400, values=form.values())
    transaction = Transaction(user_id=user.id)
    db.add(transaction)
    _save(db, user, valid, transaction)
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
    other = transaction.transfer
    amount = transaction.amount
    values = {
        "account_id": transaction.account_id,
        "transfer_account_id": other.account_id if other else None,
        "when": transaction.date.isoformat(),
        "payee": transaction.payee,
        "memo": transaction.memo,
        # On a transfer, the category may sit on the other (budget-account) leg.
        "category_id": transaction.category_id or (other.category_id if other else None),
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
    _save(db, user, valid, transaction)
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
        if transaction.transfer is not None:  # a transfer goes as a whole
            db.delete(transaction.transfer)
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
    if not transaction.takes_category:
        new_category_id = None
    transaction.category_id = new_category_id
    db.commit()

    if request.headers.get("hx-request"):
        return Response(status_code=204)
    return RedirectResponse("/transactions", status_code=303)
