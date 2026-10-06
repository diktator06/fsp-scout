import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token, generate_opaque_token, hash_opaque_token
from app.crud import refresh_session_crud
from app.models.auth_session import RefreshSession
from app.models.user import User


@dataclass(frozen=True, slots=True)
class ClientContext:
    """Сведения о клиенте, которые сохраняются в сессии и журнале согласий."""

    ip_address: str | None = None
    user_agent: str | None = None


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """Пара токенов, выданная при входе или обновлении сессии."""

    access_token: str
    access_expires_in: int
    refresh_token: str
    refresh_expires_at: datetime


async def issue_session_tokens(
    session: AsyncSession,
    user: User,
    settings: Settings,
    *,
    client: ClientContext,
    now: datetime,
    family_id: uuid.UUID | None = None,
) -> tuple[IssuedTokens, RefreshSession]:
    """Создаёт refresh-сессию и выпускает к ней access-токен.

    Без `family_id` начинается новое семейство (новый вход). При ротации семейство
    передаётся от предыдущей сессии, чтобы при краже можно было отозвать всю цепочку.
    """
    raw_refresh_token = generate_opaque_token()
    expires_at = now + timedelta(days=settings.refresh_token_ttl_days)
    refresh_session = await refresh_session_crud.create(
        session,
        {
            "user_id": user.id,
            "family_id": family_id or uuid.uuid4(),
            "token_hash": hash_opaque_token(raw_refresh_token),
            "expires_at": expires_at,
            "user_agent": (client.user_agent or "")[:512] or None,
            "ip_address": client.ip_address,
        },
    )
    access_token, expires_in = create_access_token(
        user_id=user.id,
        role=user.role.value,
        email=user.email,
        email_verified=user.is_email_verified,
        settings=settings,
        now=now,
    )
    tokens = IssuedTokens(
        access_token=access_token,
        access_expires_in=expires_in,
        refresh_token=raw_refresh_token,
        refresh_expires_at=expires_at,
    )
    return tokens, refresh_session
