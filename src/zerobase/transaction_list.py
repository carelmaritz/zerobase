"""The transactions list: filters, keyset paging, and the URLs that carry them (TASK-M005).

Filters live in the query string so a list can be bookmarked, and forms on the page send
the query string back in a hidden ``back`` field so a POST returns to the same list.
Values that don't parse are dropped, never an error: a stale bookmark still shows a list.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
from urllib.parse import parse_qsl, urlencode

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import aliased, joinedload

from .models import Account, Transaction

PAGE_SIZE = 100
UNCATEGORISED = "none"
MAX_SEARCH = 100


def _int(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value.isdigit() and len(value) < 10 else None


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError:
        return None


def _cursor(value: str | None) -> tuple[date, int] | None:
    """``2026-11-08:123`` → (date, id), the row a page starts after."""
    when, _, ident = (value or "").partition(":")
    parsed_date, parsed_id = _date(when), _int(ident)
    return (parsed_date, parsed_id) if parsed_date and parsed_id is not None else None


@dataclass(frozen=True)
class ListFilters:
    account_id: int | None = None
    category: str = ""  # "" for any, UNCATEGORISED, or a category ID as text
    start: date | None = None
    end: date | None = None
    text: str = ""
    before: tuple[date, int] | None = None  # older than this row
    after: tuple[date, int] | None = None  # newer than this row

    @classmethod
    def from_params(cls, params: Mapping[str, str]) -> ListFilters:
        category = (params.get("category") or "").strip()
        if category != UNCATEGORISED:
            category_id = _int(category)
            category = "" if category_id is None else str(category_id)
        before = _cursor(params.get("before"))
        return cls(
            account_id=_int(params.get("account_id")),
            category=category,
            start=_date(params.get("from")),
            end=_date(params.get("to")),
            text=(params.get("q") or "").strip()[:MAX_SEARCH],
            before=before,
            after=None if before else _cursor(params.get("after")),
        )

    @classmethod
    def from_back(cls, back: str) -> ListFilters:
        """From the query string a form carried in its hidden ``back`` field."""
        return cls.from_params(dict(parse_qsl(back.lstrip("?"))))

    @property
    def any_filter(self) -> bool:
        return bool(self.account_id or self.category or self.start or self.end or self.text)

    def params(self) -> dict[str, str]:
        out = {}
        if self.account_id is not None:
            out["account_id"] = str(self.account_id)
        if self.category:
            out["category"] = self.category
        if self.start:
            out["from"] = self.start.isoformat()
        if self.end:
            out["to"] = self.end.isoformat()
        if self.text:
            out["q"] = self.text
        if self.before:
            out["before"] = f"{self.before[0].isoformat()}:{self.before[1]}"
        elif self.after:
            out["after"] = f"{self.after[0].isoformat()}:{self.after[1]}"
        return out

    def query_string(self) -> str:
        return urlencode(self.params())

    def url(self) -> str:
        qs = self.query_string()
        return f"/transactions?{qs}" if qs else "/transactions"

    def first_page(self) -> ListFilters:
        return replace(self, before=None, after=None)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def filtered(user_id: int, f: ListFilters) -> Select:
    """Every transaction matching the filters, unordered and unpaged."""
    query = select(Transaction).where(Transaction.user_id == user_id)
    if f.account_id is not None:
        query = query.where(Transaction.account_id == f.account_id)
    if f.category == UNCATEGORISED:
        # The budget page's rule: on a budget account, no category, and not a transfer
        # to another budget account (that needs none). Keep in step with build_budget().
        account = aliased(Account)
        other_leg = aliased(Transaction)
        other_account = aliased(Account)
        query = (
            query.join(account, account.id == Transaction.account_id)
            .outerjoin(other_leg, other_leg.id == Transaction.transfer_id)
            .outerjoin(other_account, other_account.id == other_leg.account_id)
            .where(
                account.on_budget.is_(True),
                Transaction.category_id.is_(None),
                or_(other_account.id.is_(None), other_account.on_budget.is_(False)),
            )
        )
    elif f.category:
        query = query.where(Transaction.category_id == int(f.category))
    if f.start:
        query = query.where(Transaction.date >= f.start)
    if f.end:
        query = query.where(Transaction.date <= f.end)
    if f.text:
        pattern = f"%{_escape_like(f.text)}%"
        query = query.where(
            or_(
                Transaction.payee.ilike(pattern, escape="\\"),
                Transaction.memo.ilike(pattern, escape="\\"),
            )
        )
    return query


@dataclass
class Page:
    transactions: list[Transaction]
    older: ListFilters | None  # the next page back in time, if there is one
    newer: ListFilters | None


def _fetch(db, query: Select, limit: int) -> list[Transaction]:
    query = query.options(
        joinedload(Transaction.account),
        joinedload(Transaction.category),
        joinedload(Transaction.transfer).joinedload(Transaction.account),
    ).limit(limit)
    return list(db.scalars(query).unique().all())


def load_page(db, user_id: int, f: ListFilters, size: int = PAGE_SIZE) -> Page:
    """One page, newest first, by keyset on (date, id). One extra row says if there's more."""
    base = filtered(user_id, f)
    newest_first = (Transaction.date.desc(), Transaction.id.desc())

    if f.after:
        when, ident = f.after
        rows = _fetch(
            db,
            base.where(
                or_(Transaction.date > when, and_(Transaction.date == when, Transaction.id > ident))
            ).order_by(Transaction.date.asc(), Transaction.id.asc()),
            size + 1,
        )
        if len(rows) <= size:
            # Back at the newest rows: show the real first page, so it's always full.
            return load_page(db, user_id, f.first_page(), size)
        rows = list(reversed(rows[:size]))
        older = replace(f, after=None, before=(rows[-1].date, rows[-1].id))
        newer = replace(f, after=(rows[0].date, rows[0].id))
        return Page(rows, older, newer)

    query = base.order_by(*newest_first)
    if f.before:
        when, ident = f.before
        query = query.where(
            or_(Transaction.date < when, and_(Transaction.date == when, Transaction.id < ident))
        )
    rows = _fetch(db, query, size + 1)
    more = len(rows) > size
    rows = rows[:size]
    older = replace(f, before=(rows[-1].date, rows[-1].id)) if more and rows else None
    newer = None
    if f.before:
        newer = (
            replace(f, before=None, after=(rows[0].date, rows[0].id)) if rows else f.first_page()
        )
    return Page(rows, older, newer)
