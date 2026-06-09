from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def _engine_instance():
    global _engine, _session_factory
    if _engine is None:
        from app.config import settings
        _engine = create_async_engine(settings.database_url, echo=False)
        _session_factory = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine, _session_factory


async def get_db():
    _, factory = _engine_instance()
    async with factory() as session:
        yield session


def get_session_factory() -> async_sessionmaker:
    _, factory = _engine_instance()
    return factory
