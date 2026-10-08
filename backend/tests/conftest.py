import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://fsp:fsp@localhost:5432/fsp_scout_test"
)
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["MAIL_BACKEND"] = "console"
os.environ["SEED_DEMO_USERS"] = "false"
os.environ["WEBHOOK_DISPATCHER_ENABLED"] = "false"
os.environ["FRONTEND_URL"] = "http://scout.test"

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_mailer
from app.core.config import get_settings
from app.db.session import get_session
from app.main import app
from app.models.user import User, UserRole
from app.seed.seeders import seed_reference_data
from tests.helpers import DEFAULT_PASSWORD, RecordingMailer, create_user

BACKEND_ROOT = Path(__file__).resolve().parent.parent


async def _recreate_database() -> None:
    """Создаёт тестовую базу при первом запуске и очищает схему перед прогоном."""
    url = make_url(get_settings().database_url)
    admin = create_async_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin.connect() as connection:
        exists = await connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            await connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    await admin.dispose()

    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


async def _seed_reference_data() -> None:
    """Наполняет тестовую базу справочниками один раз на весь прогон."""
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await seed_reference_data(session)
        await session.commit()
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def prepared_database() -> Iterator[None]:
    """Готовит базу для всего прогона: чистая схема, миграции Alembic, справочники.

    Схема строится именно миграциями, а не `create_all`: так тесты заодно проверяют,
    что миграции применяются с нуля.
    """
    asyncio.run(_recreate_database())
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    command.upgrade(alembic_config, "head")
    asyncio.run(_seed_reference_data())
    yield


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Сессия БД внутри внешней транзакции, которая откатывается после теста.

    Сервисы вызывают `commit`, но в режиме `create_savepoint` он фиксирует только
    SAVEPOINT. Поэтому каждый тест видит исходные справочники и не оставляет следов.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
def mailer() -> RecordingMailer:
    """Заглушка почты: письма складываются в список и проверяются в тестах."""
    return RecordingMailer()


@pytest.fixture
async def client(db_session: AsyncSession, mailer: RecordingMailer) -> AsyncIterator[AsyncClient]:
    """HTTP-клиент к приложению с подменёнными сессией БД и почтой."""

    async def override_session() -> AsyncIterator[AsyncSession]:
        """Отдаёт тестовую сессию вместо сессии из пула приложения."""
        yield db_session

    def override_mailer() -> RecordingMailer:
        """Отдаёт заглушку почты."""
        return mailer

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_mailer] = override_mailer
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(db_session: AsyncSession) -> Callable[..., Awaitable[User]]:
    """Фабрика пользователей с заданной ролью и состоянием аккаунта."""

    async def factory(
        role: UserRole = UserRole.CANDIDATE,
        *,
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        verified: bool = True,
        active: bool = True,
    ) -> User:
        """Создаёт пользователя и фиксирует его в тестовой транзакции."""
        return await create_user(
            db_session, role, email=email, password=password, verified=verified, active=active
        )

    return factory
