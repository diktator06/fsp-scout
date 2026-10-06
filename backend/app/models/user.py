from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum


class UserRole(StrEnum):
    """Роли платформы.

    Методист ведёт справочники и банк заданий и самостоятельно не регистрируется.
    """

    CANDIDATE = "candidate"
    EMPLOYER = "employer"
    METHODIST = "methodist"


class AuthProvider(StrEnum):
    """Источник учётной записи: собственная регистрация или внешний OIDC (ФСП ID / Keycloak)."""

    LOCAL = "local"
    OIDC = "oidc"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Учётная запись пользователя любой роли."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(
            "auth_provider <> 'local' OR password_hash IS NOT NULL",
            name="local_account_has_password",
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"))
    is_email_verified: Mapped[bool] = mapped_column(default=False, server_default=false())
    email_verified_at: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    auth_provider: Mapped[AuthProvider] = mapped_column(
        pg_enum(AuthProvider, "auth_provider"),
        default=AuthProvider.LOCAL,
        server_default=AuthProvider.LOCAL.value,
    )
    external_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    last_login_at: Mapped[datetime | None]
