import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum


class SessionRevokeReason(StrEnum):
    """Почему refresh-сессия перестала действовать."""

    ROTATED = "rotated"
    LOGOUT = "logout"
    REUSE_DETECTED = "reuse_detected"
    EXPIRED = "expired"


class EmailVerificationToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Одноразовая ссылка подтверждения email. Хранится только хеш токена."""

    __tablename__ = "email_verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class RefreshSession(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Refresh-сессия пользователя.

    Сессии одного входа образуют «семейство» (`family_id`): при каждом обновлении старая
    запись отзывается и ссылается на новую. Если отозванный токен предъявят повторно,
    значит его украли, и отзывается всё семейство.
    """

    __tablename__ = "refresh_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    revoke_reason: Mapped[SessionRevokeReason | None] = mapped_column(
        pg_enum(SessionRevokeReason, "session_revoke_reason")
    )
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_sessions.id", ondelete="SET NULL")
    )
    user_agent: Mapped[str | None] = mapped_column(String(512))
    ip_address: Mapped[str | None] = mapped_column(String(45))
