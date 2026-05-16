from .database import AsyncSessionFactory


async def get_db():
    """FastAPI dependency — yields an async SQLAlchemy session."""
    async with AsyncSessionFactory() as session:
        yield session
