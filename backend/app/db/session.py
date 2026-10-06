from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


def build_engine(database_url: str | None = None) -> AsyncEngine:
    """Создаёт асинхронный движок SQLAlchemy поверх asyncpg.

    `pool_pre_ping` нужен, чтобы после перезапуска контейнера БД приложение не отдавало
    ошибки на первых запросах из-за мёртвых соединений в пуле.
    """
    settings = get_settings()
    return create_async_engine(
        database_url or settings.database_url,
        echo=settings.database_echo,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
    )


engine = build_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Отдаёт сессию БД на время одного HTTP-запроса.

    Фиксацию транзакции выполняет сервисный слой. Если запрос упал до `commit`,
    выход из контекста откатывает всё незафиксированное.
    """
    async with SessionFactory() as session:
        yield session
