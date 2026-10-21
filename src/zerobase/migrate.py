"""Schema migrations (Alembic), applied automatically when the app starts.

Developers create new revisions with the ``alembic`` command from the project root;
see "Database migrations" in the README.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Connection, Engine, inspect, text

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
# Arbitrary constant: the PostgreSQL advisory lock that serialises migrations when
# several app processes start at once.
_LOCK_ID = 7_294_015_331


class UnmigratedDatabaseError(RuntimeError):
    """The database has Zerobase tables but no migration history."""


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def upgrade_to_head(engine: Engine) -> str | None:
    """Bring the database up to the latest revision and return that revision."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": _LOCK_ID})
        tables = set(inspect(connection).get_table_names())
        if "users" in tables and "alembic_version" not in tables:
            # Created by a pre-migration build with create_all. Guessing its revision could
            # corrupt data, so stop and let a person decide.
            raise UnmigratedDatabaseError(
                "This database was created by a Zerobase version without migrations and "
                "cannot be upgraded in place. Back it up with scripts/backup.sh if you want "
                "to keep it, then start Zerobase with an empty database."
            )
        command.upgrade(alembic_config(connection), "head")
        return current_revision(connection)
