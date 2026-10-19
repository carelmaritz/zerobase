from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings, get_settings
from .db import Base, make_engine, make_session_factory
from .deps import NotAuthenticated
from .routers import accounts, auth, budget, transactions
from .security import LoginThrottle
from .templating import PACKAGE_DIR, make_templates

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.env == "production" and len(settings.secret_key) < 32:
        raise RuntimeError(
            "ZEROBASE_SECRET_KEY must be set to a random value of at least 32 characters "
            "(generate one with: openssl rand -hex 32)"
        )

    engine = make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="Zerobase",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.templates = make_templates(settings.currency_symbol)
    app.state.login_throttle = LoginThrottle()

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key or "insecure-non-production-key",
        session_cookie="zerobase_session",
        max_age=14 * 24 * 3600,
        same_site="lax",
        https_only=settings.https_only,
    )

    @app.middleware("http")
    async def protect(request: Request, call_next):
        # Defence in depth on top of SameSite=Lax cookies: refuse cross-origin form posts.
        if request.method not in SAFE_METHODS:
            source = request.headers.get("origin") or request.headers.get("referer")
            if source and urlsplit(source).netloc != request.headers.get("host", ""):
                return PlainTextResponse("Cross-site request blocked.", status_code=403)
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @app.exception_handler(NotAuthenticated)
    async def redirect_to_login(request: Request, _: NotAuthenticated) -> Response:
        if request.headers.get("hx-request"):
            return Response(status_code=204, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", status_code=303)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    for module in (auth, budget, accounts, transactions):
        app.include_router(module.router)
    return app
