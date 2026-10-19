from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .models import Account, Category, User


class NotAuthenticated(Exception):
    """Raised when a page needs a signed-in user."""


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as db:
        yield db


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("uid")
    user = db.get(User, user_id) if isinstance(user_id, int) else None
    if user is None:
        request.session.clear()
        raise NotAuthenticated
    return user


def owned_category(db: Session, user: User, category_id: int) -> Category:
    category = db.get(Category, category_id)
    if category is None or category.user_id != user.id:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


def owned_account(db: Session, user: User, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    return account
