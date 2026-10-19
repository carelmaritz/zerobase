from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..budget import account_balances
from ..deps import current_user, get_db
from ..models import Account, Transaction, User
from ..money import parse_money
from ..templating import render

router = APIRouter()

ACCOUNT_KINDS = {"checking": "Checking", "savings": "Savings", "cash": "Cash", "other": "Other"}


def _page(request: Request, db: Session, user: User, error: str | None = None, status: int = 200):
    context = {
        "user": user,
        "active": "accounts",
        "accounts": account_balances(db, user.id),
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
    name = name.strip()
    if not 0 < len(name) <= 80:
        return _page(request, db, user, "Give the account a name (up to 80 characters).", 400)
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
        # A positive opening balance in a budget account is money to assign.
        db.add(
            Transaction(
                user_id=user.id,
                account_id=account.id,
                date=date.today(),
                payee="Starting balance",
                amount=balance,
            )
        )
    db.commit()
    return RedirectResponse("/accounts", status_code=303)
