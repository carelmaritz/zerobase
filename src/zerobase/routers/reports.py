"""The reports page (TASK-M003)."""

from calendar import month_name
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import charts
from ..deps import current_user, get_db
from ..models import Transaction, User
from ..money import format_money
from ..reports import MonthRange, cash_flow, net_worth
from ..templating import render

router = APIRouter()

NAMES = {
    "income": "Income",
    "spending": "Spending",
    "cash": "Cash and other",
    "investments": "Investments",
    "property": "Property",
    "debt": "Debt",
}


def _month(params, name: str) -> date | None:
    """From the form's month and year selects; None (the default) if they don't parse."""
    month, year = params.get(f"{name}_month", ""), params.get(f"{name}_year", "")
    try:
        parsed = date(int(year), int(month), 1)
    except ValueError:
        return None
    return parsed if 1990 <= parsed.year <= 2100 else None


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)
):
    today = date.today()
    params = request.query_params
    months = MonthRange.build(_month(params, "from"), _month(params, "to"), today)
    flow = cash_flow(db, user.id, months)
    worth = net_worth(db, user.id, months, today)
    labels = [f"{m:%b %Y}" for m in months.months]

    symbol = request.app.state.settings.currency_symbol

    def money(minor: int) -> str:
        return format_money(minor, symbol)

    earliest = db.scalar(select(func.min(Transaction.date)).where(Transaction.user_id == user.id))
    first_year = min([months.start.year, *([earliest.year] if earliest else [])])
    parts = {
        "cash": worth.cash,
        "investments": worth.investments,
        "property": worth.property,
        "debt": worth.debt,
    }
    categories = [(c.name, c.total) for g in flow.groups for c in g.categories]
    context = {
        "user": user,
        "active": "reports",
        "range": months,
        "labels": labels,
        "month_names": list(month_name)[1:],
        "years": range(today.year, first_year - 1, -1),
        "flow": flow,
        "worth": worth,
        "names": NAMES,
        "has_worth": any(any(amounts) for amounts in parts.values()),
        "flow_chart": charts.grouped(
            labels, {"income": flow.income, "spending": flow.spending}, NAMES, money
        ),
        "worth_chart": charts.stacked(labels, parts, worth.total, NAMES, money),
        "spending_chart": charts.ranked(categories),
    }
    return render(request, "reports.html", context)
