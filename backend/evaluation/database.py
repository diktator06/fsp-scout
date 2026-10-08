from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.seed.seeders import seed_reference_data

BACKEND_ROOT = Path(__file__).resolve().parents[1]
EVALUATION_SUFFIX = "_eval"


def ensure_evaluation_database(url: str) -> None:
    """Оценка пересоздаёт схему базы, поэтому работает только с базой `*_eval`.

    Иначе случайный запуск без переменной окружения стёр бы данные стенда.
    """
    name = make_url(url).database or ""
    if not name.endswith(EVALUATION_SUFFIX):
        raise SystemExit(
            f"Оценка запускается только на отдельной базе *{EVALUATION_SUFFIX}, а не на «{name}». "
            "Используйте `make eval-matching`."
        )


async def recreate_database(url: str) -> None:
    """Создаёт базу при первом запуске и очищает схему перед прогоном."""
    parsed = make_url(url)
    admin = create_async_engine(
        parsed.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin.connect() as connection:
        exists = await connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
        )
        if not exists:
            await connection.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    await admin.dispose()
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


def migrate() -> None:
    """Применяет миграции Alembic — схема строится так же, как на стенде."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(config, "head")


async def seed_dictionaries(url: str) -> None:
    """Справочники и банк заданий — те же, что на стенде."""
    engine = create_async_engine(url, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await seed_reference_data(session)
        await session.commit()
    await engine.dispose()
