import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.crud import user_crud
from app.integrations.mailer import OutgoingEmail
from app.models.user import User, UserRole

DEFAULT_PASSWORD = "Sk0ut-test-2026"
_TOKEN_IN_LINK = re.compile(r"/auth/verify\?token=([A-Za-z0-9_\-]+)")


class RecordingMailer:
    """Почта для тестов: ничего не отправляет, только запоминает письма."""

    def __init__(self) -> None:
        """Создаёт пустой ящик исходящих."""
        self.outbox: list[OutgoingEmail] = []

    async def send(self, message: OutgoingEmail) -> None:
        """Складывает письмо в ящик."""
        self.outbox.append(message)

    def last_verification_token(self) -> str:
        """Достаёт токен из ссылки подтверждения в последнем письме."""
        assert self.outbox, "Писем не было"
        match = _TOKEN_IN_LINK.search(self.outbox[-1].text_body)
        assert match, "В письме нет ссылки подтверждения"
        return match.group(1)


def unique_email(prefix: str = "user") -> str:
    """Уникальный email для теста."""
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


async def create_user(
    session: AsyncSession,
    role: UserRole = UserRole.CANDIDATE,
    *,
    email: str | None = None,
    password: str = DEFAULT_PASSWORD,
    verified: bool = True,
    active: bool = True,
) -> User:
    """Создаёт пользователя напрямую через CRUD, минуя сценарий регистрации."""
    user = await user_crud.create_local(
        session,
        email=email or unique_email(role.value),
        password_hash=hash_password(password),
        role=role,
        is_email_verified=verified,
        verified_at=datetime.now(UTC) if verified else None,
    )
    if not active:
        await user_crud.update(session, user, {"is_active": False})
    await session.commit()
    return user


def auth_headers(user: User) -> dict[str, str]:
    """Заголовок авторизации с действующим access-токеном пользователя."""
    token, _ = create_access_token(
        user_id=user.id,
        role=user.role.value,
        email=user.email,
        email_verified=user.is_email_verified,
        settings=get_settings(),
    )
    return {"Authorization": f"Bearer {token}"}
