from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..budget import (
    account_balances,
    add_payment_category,
    category_in_use,
    cleared_balances,
    inflow_category,
)
from ..deps import current_user, get_db, owned_account
from ..models import (
    CLEARED,
    CREDIT_CARD,
    Account,
    Category,
    ImportMapping,
    ScheduledTransaction,
    Transaction,
    User,
)
from ..money import parse_money
from ..schedules import delete_schedule
from ..templating import render

router = APIRouter()

ACCOUNT_KINDS = {
    "checking": "Current account",  # the stored key stays "checking"; UK name shown
    "savings": "Savings",
    "cash": "Cash",
    "other": "Other",
    CREDIT_CARD: "Credit card",
}
NAME_ERROR = "Give the account a name (up to 80 characters)."


def _clean_name(name: str) -> str | None:
    name = name.strip()
    return name if 0 < len(name) <= 80 else None


def _page(request: Request, db: Session, user: User, error: str | None = None, status: int = 200):
    balances = account_balances(db, user.id)
    context = {
        "user": user,
        "active": "accounts",
        "accounts": [(a, b) for a, b in balances if not a.closed],
        "closed_accounts": [(a, b) for a, b in balances if a.closed],
        "cleared": cleared_balances(db, user.id),
        "kinds": ACCOUNT_KINDS,
        "error": error,
    }
    return render(request, "accounts.html", context, status_code=status)


@router.get("/accounts", response_class=HTMLResponse)
def accounts_page(
    request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    return _page(request, db, user)


@router.post("/accounts")
def add_account(
    request: Request,
    name: str = Form(...),
    kind: str = Form("checking"),
    on_budget: str | None = Form(None),
    opening_balance: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    name = _clean_name(name)
    if name is None:
        return _page(request, db, user, NAME_ERROR, 400)
    if kind not in ACCOUNT_KINDS:
        kind = "other"
    try:
        balance = parse_money(opening_balance) if opening_balance.strip() else 0
    except ValueError as exc:
        return _page(request, db, user, f"Opening balance: {exc}", 400)

    card = kind == CREDIT_CARD
    account = Account(
        user_id=user.id, name=name, kind=kind, on_budget=card or on_budget is not None
    )
    db.add(account)
    db.flush()
    category_id = None
    if card:
        # Debt on a new card is filed under its payment category: it shows there as needed,
        # without touching Ready to Assign. A card in credit is money to assign.
        payment = add_payment_category(db, account)
        if balance < 0:
            category_id = payment.id
    if account.on_budget and category_id is None:
        # A budget account's opening balance is money to assign (or owed, if negative).
        category_id = inflow_category(db, user.id).id
    if balance:
        db.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                category_id=category_id,
                date=date.today(),
                payee="Starting balance",
                amount=balance,
                status=CLEARED,  # what the bank showed when the account was added
            )
        )
    db.commit()
    return RedirectResponse("/accounts", status_code=303)


def _balance(db: Session, account: Account) -> int:
    total = db.scalar(
        select(func.sum(Transaction.amount)).where(Transaction.account_id == account.id)
    )
    return int(total or 0)


def _has_transactions(db: Session, account: Account) -> bool:
    found = db.scalar(select(Transaction.id).where(Transaction.account_id == account.id).limit(1))
    return found is not None


def _edit_page(
    request: Request,
    db: Session,
    user: User,
    account: Account,
    error: str | None = None,
    status: int = 200,
    name: str | None = None,
    close_refused: bool = False,
):
    context = {
        "user": user,
        "active": "accounts",
        "account": account,
        "name": account.name if name is None else name,
        "balance": _balance(db, account),
        "has_transactions": _has_transactions(db, account),
        "kinds": ACCOUNT_KINDS,
        "error": error,
        "close_refused": close_refused,
    }
    return render(request, "account_edit.html", context, status_code=status)


def _back() -> RedirectResponse:
    return RedirectResponse("/accounts", status_code=303)


def _payment_category(db: Session, account: Account) -> Category | None:
    return db.scalar(select(Category).where(Category.account_id == account.id))


@router.get("/accounts/{account_id}/edit", response_class=HTMLResponse)
def edit_account_form(
    request: Request,
    account_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return _edit_page(request, db, user, owned_account(db, user, account_id))


@router.post("/accounts/{account_id}/edit")
def edit_account(
    request: Request,
    account_id: int,
    name: str = Form(...),
    kind: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Rename and change the type. Budget/tracking is fixed: changing it would rewrite history."""
    account = owned_account(db, user, account_id)
    cleaned = _clean_name(name)
    if cleaned is None:
        return _edit_page(request, db, user, account, NAME_ERROR, 400, name=name)
    # A card's type is fixed: its payment category and history depend on it.
    if kind not in ACCOUNT_KINDS or (kind == CREDIT_CARD) != account.is_credit_card:
        error = "Choose a valid account type."
        return _edit_page(request, db, user, account, error, 400, name=name)
    account.name, account.kind = cleaned, kind
    payment = _payment_category(db, account)
    if payment is not None:  # a card's payment category is named after it
        payment.name = cleaned[:60]
    db.commit()
    return _back()


@router.post("/accounts/{account_id}/close")
def close_account(
    request: Request,
    account_id: int,
    closed: bool = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Close (only at a zero balance) or reopen. A closed account's history still counts."""
    account = owned_account(db, user, account_id)
    if closed and not account.closed and _balance(db, account):
        return _edit_page(request, db, user, account, status=400, close_refused=True)
    account.closed = closed
    payment = _payment_category(db, account)
    if payment is not None:  # hidden while the card is closed; it still counts
        payment.hidden = closed
    db.commit()
    return _back()


@router.post("/accounts/{account_id}/delete")
def delete_account(
    request: Request,
    account_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Delete an account created by mistake. One with transactions can only be closed."""
    account = owned_account(db, user, account_id)
    if _has_transactions(db, account):
        error = f"{account.name} has transactions, so it can't be deleted. Close it instead."
        return _edit_page(request, db, user, account, error, 400)
    payment = _payment_category(db, account)
    if payment is not None:
        if category_in_use(db, payment):
            error = (
                f"Money has been assigned to {account.name}'s payment category, so it can't "
                "be deleted. Close it instead."
            )
            return _edit_page(request, db, user, account, error, 400)
        db.delete(payment)
    # Its saved import settings and schedules go too (SQLite doesn't enforce the CASCADE).
    for saved in db.scalars(select(ImportMapping).where(ImportMapping.account_id == account.id)):
        db.delete(saved)
    for schedule in db.scalars(
        select(ScheduledTransaction).where(
            or_(
                ScheduledTransaction.account_id == account.id,
                ScheduledTransaction.transfer_account_id == account.id,
            )
        )
    ):
        delete_schedule(db, schedule)
    db.flush()  # the category and settings refer to the account
    db.delete(account)
    db.commit()
    return _back()
