"""Updating a tracking account's value (TASK-M007).

Investments (and houses, mortgages...) change value without any spending. The user enters
what the account is worth on a date; the difference from its balance on that date is added
as one cleared "Market value change" transaction, with no category: tracking accounts never
touch the budget.
"""

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import current_user, get_db, owned_account
from ..investments import parse_quantity
from ..models import CLEARED, CRYPTO, Account, Transaction, User
from ..money import parse_money
from ..templating import render

router = APIRouter()

VALUE_PAYEE = "Market value change"


def _account(db: Session, user: User, account_id: int) -> Account:
    account = owned_account(db, user, account_id)
    # On a budget account a value change would be made-up income; a closed one is empty.
    if account.on_budget or account.closed:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


def _balance_on(db: Session, account: Account, on: date) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                Transaction.account_id == account.id, Transaction.date <= on
            )
        )
    )


def _page(request, db, user, account, values=None, error=None, status=200):
    today = date.today()
    balance = _balance_on(db, account, today)
    context = {
        "user": user,
        "active": "accounts",
        "account": account,
        "balance": balance,
        "crypto": account.kind == CRYPTO,
        "values": values
        or {"value": "", "when": today.isoformat(), "quantity": account.quantity_text},
        "error": error,
    }
    return render(request, "account_value.html", context, status_code=status)


@router.get("/accounts/{account_id}/value", response_class=HTMLResponse)
def value_page(
    request: Request,
    account_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return _page(request, db, user, _account(db, user, account_id))


@router.post("/accounts/{account_id}/value")
def update_value(
    request: Request,
    account_id: int,
    value: str = Form(""),
    when: str = Form(""),
    quantity: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    account = _account(db, user, account_id)
    values = {"value": value, "when": when, "quantity": quantity}

    def refuse(message: str):
        return _page(request, db, user, account, values, message, 400)

    try:
        worth = parse_money(value)
    except ValueError as exc:
        return refuse(f"Value: {exc}")
    try:
        on = date.fromisoformat(when.strip())
    except ValueError:
        return refuse("Choose a valid date.")
    if not 1990 <= on.year <= 2100:
        return refuse("Choose a date between 1990 and 2100.")
    held = None
    if account.kind == CRYPTO:
        try:
            held = parse_quantity(quantity)
        except ValueError as exc:
            return refuse(str(exc))

    # One update at a time per account, and the difference is worked out afresh on every
    # post, so saving the same value twice adds it only once.
    db.execute(select(Account.id).where(Account.id == account.id).with_for_update())
    difference = worth - _balance_on(db, account, on)
    if difference:
        db.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                category_id=None,
                date=on,
                payee=VALUE_PAYEE,
                amount=difference,
                status=CLEARED,
            )
        )
    if account.kind == CRYPTO:
        account.quantity = held
    db.commit()
    return RedirectResponse("/accounts", status_code=303)
