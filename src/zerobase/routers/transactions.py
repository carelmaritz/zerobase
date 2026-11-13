from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..budget import account_balances, cleared_balances, inflow_category
from ..deps import current_user, get_db, owned_category, owned_transaction
from ..entry import TransactionForm, save_transaction, transaction_form, validate_transaction
from ..models import (
    CLEARED,
    RECONCILED,
    STATUSES,
    UNCLEARED,
    Account,
    Category,
    CategoryGroup,
    Transaction,
    User,
)
from ..money import plain_money
from ..schedules import upcoming
from ..templating import render
from ..transaction_list import UNCATEGORISED, ListFilters, load_page

router = APIRouter()

UPCOMING_DAYS = 30  # how far ahead the list's Upcoming section looks (TASK-M002)


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
    filters: ListFilters,
    error: str | None = None,
    status: int = 200,
    values: dict | None = None,
):
    page = load_page(db, user.id, filters)
    account_id = filters.account_id
    summary = None
    if account_id is not None:
        balance = dict((a.id, b) for a, b in account_balances(db, user.id)).get(account_id)
        if balance is not None:  # one of this user's accounts
            cleared = cleared_balances(db, user.id).get(account_id, 0)
            summary = {"cleared": cleared, "uncleared": balance - cleared, "balance": balance}
    context = {
        "user": user,
        "active": "transactions",
        "transactions": page.transactions,
        "older_url": page.older.url() if page.older else None,
        "newer_url": page.newer.url() if page.newer else None,
        **_pickers(db, user),
        "filters": filters,
        "summary": summary,
        "uncategorised": UNCATEGORISED,
        "back": filters.query_string(),
        "account_id": account_id,
        "values": values or {"account_id": account_id, "when": date.today().isoformat()},
        "upcoming": upcoming(db, user.id, date.today(), UPCOMING_DAYS, account_id),
        "upcoming_days": UPCOMING_DAYS,
        "error": error,
    }
    return render(request, "transactions.html", context, status_code=status)


@router.get("/transactions", response_class=HTMLResponse)
def transactions_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    # Read by hand: "from" is a Python keyword, and bad values are dropped, not refused.
    return _page(request, db, user, ListFilters.from_params(request.query_params))


def _back_to(back: str) -> RedirectResponse:
    """Back to the list the form came from. Rebuilt from known filters: never a free URL."""
    return RedirectResponse(ListFilters.from_back(back).url(), status_code=303)


@router.post("/transactions")
def add_transaction(
    request: Request,
    form: TransactionForm = Depends(transaction_form),
    back: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    valid = validate_transaction(db, user, form)
    if isinstance(valid, str):
        filters = ListFilters.from_back(back)
        return _page(request, db, user, filters, error=valid, status=400, values=form.values())
    transaction = Transaction(user_id=user.id)
    db.add(transaction)
    save_transaction(db, user.id, valid, transaction)
    db.commit()
    return _back_to(back)


def _edit_page(
    request: Request,
    db: Session,
    user: User,
    transaction: Transaction,
    values: dict,
    back: str,
    error: str | None = None,
    status: int = 200,
):
    context = {
        "user": user,
        "active": "transactions",
        "transaction": transaction,
        "locked": _locked(transaction),
        "statuses": STATUSES,
        **_pickers(db, user),
        "values": values,
        "back": ListFilters.from_back(back).query_string(),
        "back_url": ListFilters.from_back(back).url(),
        "error": error,
    }
    return render(request, "transaction_edit.html", context, status_code=status)


@router.get("/transactions/{transaction_id}/edit", response_class=HTMLResponse)
def edit_transaction_form(
    request: Request,
    transaction_id: int,
    back: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    transaction = owned_transaction(db, user, transaction_id)
    return _edit_page(request, db, user, transaction, _values_of(transaction), back)


def _values_of(transaction: Transaction) -> dict:
    """The edit form's fields, filled from a saved transaction."""
    other = transaction.transfer
    amount = transaction.amount
    return {
        "account_id": transaction.account_id,
        "transfer_account_id": other.account_id if other else None,
        "when": transaction.date.isoformat(),
        "payee": transaction.payee,
        "memo": transaction.memo,
        # On a transfer, the category may sit on the other (budget-account) leg.
        "category_id": transaction.category_id or (other.category_id if other else None),
        "outflow": plain_money(-amount) if amount < 0 else "",
        "inflow": plain_money(amount) if amount > 0 else "",
        "status": transaction.status,
    }


def _locked(transaction: Transaction) -> bool:
    """Reconciled, on either side of a transfer: changing it needs a confirmation."""
    other = transaction.transfer
    return transaction.status == RECONCILED or (other is not None and other.status == RECONCILED)


LOCKED_ERROR = (
    "This transaction is reconciled: it matched the bank's balance. "
    "Tick “Yes, change a reconciled transaction” to change or delete it."
)


@router.post("/transactions/{transaction_id}/edit")
def edit_transaction(
    request: Request,
    transaction_id: int,
    form: TransactionForm = Depends(transaction_form),
    back: str = Form(""),
    status: str = Form(""),
    confirm_reconciled: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    transaction = owned_transaction(db, user, transaction_id)
    status = status if status in STATUSES else transaction.status
    values = {**form.values(), "status": status}
    if _locked(transaction) and confirm_reconciled != "1":
        return _edit_page(request, db, user, transaction, values, back, LOCKED_ERROR, 400)
    valid = validate_transaction(db, user, form, existing=transaction)
    if isinstance(valid, str):
        return _edit_page(request, db, user, transaction, values, back, valid, 400)
    save_transaction(db, user.id, valid, transaction)
    transaction.status = status
    db.commit()
    return _back_to(back)


@router.post("/transactions/{transaction_id}/delete")
def delete_transaction(
    request: Request,
    transaction_id: int,
    back: str = Form(""),
    confirm_reconciled: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    transaction = db.get(Transaction, transaction_id)
    if transaction is not None and transaction.user_id == user.id:
        if _locked(transaction) and confirm_reconciled != "1":
            values = _values_of(transaction)
            return _edit_page(request, db, user, transaction, values, back, LOCKED_ERROR, 400)
        if transaction.transfer is not None:  # a transfer goes as a whole
            db.delete(transaction.transfer)
        db.delete(transaction)
        db.commit()
    return _back_to(back)


@router.post("/transactions/{transaction_id}/cleared")
def toggle_cleared(
    request: Request,
    transaction_id: int,
    back: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Uncleared ↔ cleared. A reconciled row is changed on its edit page, with confirmation."""
    transaction = owned_transaction(db, user, transaction_id)
    if transaction.status == RECONCILED:
        raise HTTPException(status_code=400, detail="Reconciled: change it on its edit page")
    transaction.status = UNCLEARED if transaction.status == CLEARED else CLEARED
    db.commit()
    if request.headers.get("hx-request"):
        context = {"t": transaction, "back": ListFilters.from_back(back).query_string()}
        return render(request, "_status_cell.html", context)
    return _back_to(back)


@router.post("/transactions/{transaction_id}/category")
def set_category(
    request: Request,
    transaction_id: int,
    category_id: str = Form(""),
    back: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    transaction = db.get(Transaction, transaction_id)
    if transaction is None or transaction.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    new_category_id = None
    if category_id.strip():
        try:
            category = owned_category(db, user, int(category_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid category") from None
        if category.is_card_payment and category.id != transaction.category_id:
            raise HTTPException(status_code=400, detail="Invalid category")
        new_category_id = category.id
    if not transaction.takes_category:
        new_category_id = None
    transaction.category_id = new_category_id
    db.commit()

    if request.headers.get("hx-request"):
        return Response(status_code=204)
    return _back_to(back)
