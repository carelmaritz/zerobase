"""Alembic environment.

The app passes in an open connection (``zerobase.migrate``). The ``alembic`` command line
has none, so it connects to ``ZEROBASE_DATABASE_URL`` like the app does.
"""

from logging.config import fileConfig

from alembic import context

from zerobase import models  # noqa: F401  (registers the tables on Base.metadata)
from zerobase.config import Settings
from zerobase.db import Base, make_engine


def run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=True,  # SQLite can only ALTER by copying the table
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)  # alembic.ini, when run from the CLI

connection = context.config.attributes.get("connection")
if connection is not None:
    run_migrations(connection)
else:
    engine = make_engine(Settings().database_url)
    with engine.connect() as cli_connection:
        run_migrations(cli_connection)
        cli_connection.commit()
    engine.dispose()
