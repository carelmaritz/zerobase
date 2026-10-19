import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..budget import seed_default_categories
from ..deps import get_db
from ..models import User
from ..security import hash_password, needs_rehash, verify_password
from ..templating import render

router = APIRouter()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 10


def registration_open(request: Request, db: Session) -> bool:
    if request.app.state.settings.allow_registration:
        return True
    return db.scalar(select(func.count(User.id))) == 0


def _login_page(request: Request, db: Session, error: str | None = None, status: int = 200):
    context = {"error": error, "registration_open": registration_open(request, db)}
    return render(request, "login.html", context, status_code=status)


def _start_session(request: Request, user: User) -> None:
    request.session.clear()  # never reuse a pre-login session
    request.session["uid"] = user.id


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, db: Session = Depends(get_db)):
    if request.session.get("uid"):
        return RedirectResponse("/budget", status_code=303)
    return _login_page(request, db)


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    throttle = request.app.state.login_throttle
    key = f"{request.client.host if request.client else '?'}|{email}"
    if throttle.blocked(key):
        return _login_page(request, db, "Too many attempts. Try again in a few minutes.", 429)

    user = db.scalar(select(User).where(User.email == email))
    if not verify_password(user.password_hash if user else None, password):
        throttle.record_failure(key)
        return _login_page(request, db, "Incorrect email or password.", 400)

    throttle.reset(key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        db.commit()
    _start_session(request, user)
    return RedirectResponse("/budget", status_code=303)


@router.get("/register", response_class=HTMLResponse)
def register_form(request: Request, db: Session = Depends(get_db)):
    if not registration_open(request, db):
        return RedirectResponse("/login", status_code=303)
    return render(request, "register.html", {"error": None})


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    if not registration_open(request, db):
        return render(request, "login.html", {"error": "Registration is closed."}, 403)

    email = email.strip().lower()
    error = None
    if not EMAIL_RE.match(email) or len(email) > 254:
        error = "Enter a valid email address."
    elif len(password) < MIN_PASSWORD_LENGTH:
        error = f"Use a password of at least {MIN_PASSWORD_LENGTH} characters."
    elif db.scalar(select(User).where(User.email == email)):
        error = "That email is already registered."
    if error:
        return render(request, "register.html", {"error": error}, status_code=400)

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.flush()
    seed_default_categories(db, user.id)
    db.commit()
    _start_session(request, user)
    return RedirectResponse("/accounts", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
