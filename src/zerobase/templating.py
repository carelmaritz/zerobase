from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .deps import ENTERED_KEY
from .money import format_money, plain_money

PACKAGE_DIR = Path(__file__).parent


def make_templates(currency_symbol: str) -> Jinja2Templates:
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    templates.env.filters["money"] = lambda minor: format_money(minor, currency_symbol)
    templates.env.filters["plain"] = plain_money
    templates.env.globals["currency"] = currency_symbol
    return templates


def render(
    request: Request, name: str, context: dict | None = None, status_code: int = 200
) -> HTMLResponse:
    context = dict(context or {})
    # A full page shows (and clears) the "scheduled transactions entered" notice. Partials
    # (names starting with "_") leave it for the next full page.
    if not name.startswith("_") and "session" in request.scope:
        context.setdefault("scheduled_entered", request.session.pop(ENTERED_KEY, 0))
    return request.app.state.templates.TemplateResponse(
        request, name, context, status_code=status_code
    )
