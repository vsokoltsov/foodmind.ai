"""Alembic environment for migrations that orchestrate Elasticsearch APIs."""

from logging.config import fileConfig
import os

from alembic import context
from sqlalchemy import create_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    """Run migration scripts without a database connection."""
    context.configure(
        url=os.getenv("ALEMBIC_DATABASE_URL", config.get_main_option("sqlalchemy.url")),
        literal_binds=True,
        target_metadata=None,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migration scripts using a temporary SQLAlchemy context."""
    engine = create_engine(
        os.getenv("ALEMBIC_DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
