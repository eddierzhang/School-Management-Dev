from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.config import get_settings
from app.db import Base

config = context.config

# Only the CLI configures logging here; called from the app or the tests, the
# host's logging is left alone.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

if not config.get_main_option("sqlalchemy.url") or "driver://" in config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    """Write `server_default=func.now()` as `sa.func.now()`, which each database
    renders its own way, rather than Postgres's literal `now()`, which SQLite lacks."""
    if type_ == "server_default" and getattr(getattr(obj, "arg", None), "name", None) == "now":
        return "sa.func.now()"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        render_item=render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Batch mode lets ALTER-style migrations run on SQLite, which cannot alter
        # most things in place, as well as on Postgres.
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True,
                          render_item=render_item)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
