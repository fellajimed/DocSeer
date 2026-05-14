from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker

from .config import get_settings

_settings = get_settings()

# ─── async engine (FastAPI) ──────────────────────────────────────────────────
async_engine = create_async_engine(
    _settings.postgres_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionFactory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ─── sync engine (Celery workers + Alembic) ──────────────────────────────────
sync_engine = create_engine(
    _settings.postgres_sync_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

SyncSessionFactory = sessionmaker(
    sync_engine,
    autocommit=False,
    autoflush=False,
)
