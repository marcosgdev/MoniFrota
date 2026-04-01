"""
Conexão assíncrona com o PostgreSQL via SQLAlchemy 2.x + asyncpg.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker | None = None


async def get_engine():
    global _engine
    if _engine is None:
        from app.config import settings
        _engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


async def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        engine = await get_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    return _session_factory


async def init_db():
    """Cria tabelas se não existirem. Chamado no startup da aplicação."""
    from app.db import models  # noqa — registra os modelos no metadata
    engine = await get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
