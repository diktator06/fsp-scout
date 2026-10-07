import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.user import AuthProvider, User, UserRole


class UserCRUD(CRUDBase[User]):
    """Доступ к учётным записям."""

    async def get_by_email(self, session: AsyncSession, email: str) -> User | None:
        """Ищет пользователя по email (email хранится в нижнем регистре)."""
        return await session.scalar(select(User).where(User.email == email.lower()))

    async def create_local(
        self,
        session: AsyncSession,
        *,
        email: str,
        password_hash: str,
        role: UserRole,
        is_email_verified: bool = False,
        verified_at: datetime | None = None,
    ) -> User:
        """Создаёт учётную запись с входом по паролю."""
        return await self.create(
            session,
            {
                "email": email.lower(),
                "password_hash": password_hash,
                "role": role,
                "auth_provider": AuthProvider.LOCAL,
                "is_email_verified": is_email_verified,
                "email_verified_at": verified_at,
            },
        )

    async def mark_email_verified(self, session: AsyncSession, user: User, at: datetime) -> User:
        """Отмечает email подтверждённым."""
        return await self.update(
            session, user, {"is_email_verified": True, "email_verified_at": at}
        )

    async def emails_by_ids(
        self, session: AsyncSession, user_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """Email пачки пользователей по идентификаторам."""
        ids = list(set(user_ids))
        if not ids:
            return {}
        result = await session.execute(select(User.id, User.email).where(User.id.in_(ids)))
        return {row[0]: row[1] for row in result.all()}

    async def register_login(
        self, session: AsyncSession, user: User, at: datetime, new_password_hash: str | None = None
    ) -> User:
        """Фиксирует время входа и при необходимости обновляет хеш пароля."""
        values: dict[str, object] = {"last_login_at": at}
        if new_password_hash is not None:
            values["password_hash"] = new_password_hash
        return await self.update(session, user, values)


user_crud = UserCRUD(User)
