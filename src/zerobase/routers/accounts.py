from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget import account_balances, inflow_category
from ..deps import current_user, get_db, owned_account
from ..models import Account, Transaction, User
from ..money import parse_money
from ..templating import render

router = APIRouter()

ACCOUNT_KINDS = {"checking": "Checking", "savings": "Savings", "cash": "Cash", "other": "Other"}
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

    account = Account(user_id=user.id, name=name, kind=kind, on_budget=on_budget is not None)
    db.add(account)
    db.flush()
    if balance:
        # A budget account's opening balance is money to assign (or owed, if negative).
        db.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                category_id=inflow_category(db, user.id).id if account.on_budget else None,
                date=date.today(),
                payee="Starting balance",
                amount=balance,
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
    if kind not in ACCOUNT_KINDS:
        error = "Choose a valid account type."
        return _edit_page(request, db, user, account, error, 400, name=name)
    account.name, account.kind = cleaned, kind
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
    db.delete(account)
    db.commit()
    return _back()
