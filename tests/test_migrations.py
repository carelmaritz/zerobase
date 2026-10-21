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


def test_0002_moves_existing_income_into_the_inflow_category(engine):
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "0001")
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES "
                "(1, 'a@b.c', 'x', '2026-01-01'), (2, 'd@e.f', 'x', '2026-01-01')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO accounts (id, user_id, name, kind, on_budget) VALUES "
                "(1, 1, 'Current', 'checking', :t), (2, 1, 'Mortgage', 'other', :f), "
                "(3, 2, 'Current', 'checking', :t)"
            ),
            {"t": True, "f": False},
        )
        # No explicit category IDs: PostgreSQL's sequence must stay in step for the migration.
        connection.execute(
            text("INSERT INTO category_groups (user_id, name, sort_order) VALUES (1, 'Needs', 0)")
        )
        connection.execute(
            text(
                "INSERT INTO categories (user_id, group_id, name, sort_order) "
                "SELECT 1, id, 'Groceries', 0 FROM category_groups"
            )
        )
        groceries = connection.execute(text("SELECT id FROM categories")).scalar()
        connection.execute(
            text(
                "INSERT INTO transactions "
                "(id, user_id, account_id, category_id, date, payee, memo, amount) VALUES "
                "(1, 1, 1, NULL, '2026-10-01', 'Salary', '', 300000), "
                "(2, 1, 1, NULL, '2026-10-02', 'Mystery', '', -500), "
                "(3, 1, 1, :groceries, '2026-10-03', 'Refund', '', 700), "
                "(4, 1, 2, NULL, '2026-10-04', 'Start', '', 900000), "
                "(5, 2, 3, NULL, '2026-10-05', 'Salary', '', 1000)"
            ),
            {"groceries": groceries},
        )

    upgrade_to_head(engine)
    with engine.connect() as connection:
        inflow = dict(
            connection.execute(
                text(
                    "SELECT user_id, id FROM categories WHERE kind = 'inflow' AND group_id IS NULL"
                )
            ).all()
        )
        assert set(inflow) == {1, 2}
        rows = dict(connection.execute(text("SELECT id, category_id FROM transactions")).all())
        assert rows == {1: inflow[1], 2: None, 3: groceries, 4: None, 5: inflow[2]}
        kind = connection.execute(
            text("SELECT kind FROM categories WHERE id = :id"), {"id": groceries}
        ).scalar()
        assert kind == "standard"

    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0001")
        rows = dict(connection.execute(text("SELECT id, category_id FROM transactions")).all())
        assert rows == {1: None, 2: None, 3: groceries, 4: None, 5: None}
        assert connection.execute(text("SELECT count(*) FROM categories")).scalar() == 1
