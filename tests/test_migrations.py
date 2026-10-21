"""The migrations must build exactly the schema the models describe, on every backend."""

import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from zerobase.db import Base, make_engine
from zerobase.migrate import (
    UnmigratedDatabaseError,
    alembic_config,
    current_revision,
    upgrade_to_head,
)


@pytest.fixture
def engine():
    engine = make_engine(os.environ.get("ZEROBASE_TEST_DATABASE_URL", "sqlite://"))
    yield engine
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    engine.dispose()


def app_tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


def test_upgrade_reaches_head_and_matches_the_models(engine):
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert upgrade_to_head(engine) == head

    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_upgrade_is_idempotent(engine):
    first = upgrade_to_head(engine)
    assert upgrade_to_head(engine) == first


def test_downgrade_to_base_and_back(engine):
    upgrade_to_head(engine)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "base")
        assert current_revision(connection) is None
    assert app_tables(engine) == set()

    upgrade_to_head(engine)
    assert app_tables(engine) == set(Base.metadata.tables)


def test_refuses_a_database_created_without_migrations(engine):
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO users (email, password_hash, created_at) VALUES ('a@b.c', 'x', :t)"),
            {"t": "2026-01-01 00:00:00"},
        )

    with pytest.raises(UnmigratedDatabaseError):
        upgrade_to_head(engine)

    assert "alembic_version" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 1
