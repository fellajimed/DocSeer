"""
Alembic environment configuration.

Uses a *synchronous* SQLAlchemy URL (psycopg2) so that Alembic's default
run_migrations_online() path works without any additional async scaffolding.
The URL is read from DOCSEER_POSTGRES_SYNC_URL (or falls back to the
hard-coded default that matches docker-compose.yaml).
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ── make backend importable from the project root ────────────────────────────
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)

from backend.app.models.paper import Base  # noqa: E402 — must come after sys.path

# ── Alembic Config object ─────────────────────────────────────────────────────
config = context.config

# Inject the DB URL from the environment (overrides the blank in alembic.ini)
_sync_url = os.environ.get(
    "DOCSEER_POSTGRES_SYNC_URL",
    "postgresql+psycopg2://docseer:docseer@postgres:5432/docseer",
)
config.set_main_option("sqlalchemy.url", _sync_url)

# Interpret the config file for logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our ORM metadata for --autogenerate support
target_metadata = Base.metadata


# ── offline mode ─────────────────────────────────────────────────────────────


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emit SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── online mode ───────────────────────────────────────────────────────────────


def run_migrations_online() -> None:
    """Run migrations with a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
