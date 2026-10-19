"""Test fixtures.

By default the tests run against in-memory SQLite. Set ZEROBASE_TEST_DATABASE_URL to a
throwaway PostgreSQL database to run the exact same tests against Postgres (CI does this).
"""

import os

import pytest
from fastapi.testclient import TestClient

from zerobase.config import Settings
from zerobase.db import Base
from zerobase.main import create_app


@pytest.fixture
def app():
    settings = Settings(
        env="test",
        database_url=os.environ.get("ZEROBASE_TEST_DATABASE_URL", "sqlite://"),
        secret_key="t" * 40,
        allow_registration=False,
    )
    application = create_app(settings)
    yield application
    Base.metadata.drop_all(application.state.engine)  # leave a shared database clean
    application.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db(client, app):
    # Depends on `client` so the lifespan has created the tables first.
    with app.state.session_factory() as session:
        yield session
