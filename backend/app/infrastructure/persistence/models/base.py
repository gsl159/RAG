from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _is_sqlite(url: str) -> bool:
    return "sqlite" in url


def get_engine(database_url: str):
    global _engine
    if _engine is None:
        kwargs: dict = dict(echo=False)
        if _is_sqlite(database_url):
            kwargs.update(
                poolclass=NullPool,
                connect_args={"check_same_thread": False},
            )
        else:
            kwargs.update(
                pool_size=20,
                max_overflow=40,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
        _engine = create_async_engine(database_url, **kwargs)
    return _engine


def get_session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        engine = get_engine(database_url)
        _session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _session_factory


async def init_database(database_url: str, max_retries: int = 3):
    """Create all database tables with exponential-backoff retry.

    Args:
        database_url: The SQLAlchemy database URL (e.g. PostgreSQL or SQLite).
        max_retries: Maximum number of connection attempts (default 3).

    Raises:
        The last exception encountered if all retries are exhausted.
    """
    import asyncio

    engine = get_engine(database_url)
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2**attempt)
