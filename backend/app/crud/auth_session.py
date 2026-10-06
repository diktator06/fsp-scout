import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.auth_session import EmailVerificationToken, RefreshSession, SessionRevokeReason


class EmailVerificationTokenCRUD(CRUDBase[EmailVerificationToken]):
    """Доступ к токенам подтверждения email."""

    async def get_by_hash(
        self, session: AsyncSession, token_hash: str
    ) -> EmailVerificationToken | None:
        """Находит токен по хешу и блокирует строку до конца транзакции.

        Блокировка (`FOR UPDATE`) нужна на случай двойного клика по ссылке: второй запрос
        дождётся первого и увидит, что токен уже использован.
        """
        statement = (
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token_hash == token_hash)
            .with_for_update()
        )
        return await session.scalar(statement)

    async def invalidate_active(
        self, session: AsyncSession, user_id: uuid.UUID, at: datetime
    ) -> None:
        """Гасит все неиспользованные токены пользователя.

        Действительной остаётся только ссылка из последнего письма.
        """
        await session.execute(
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.used_at.is_(None),
            )
            .values(used_at=at)
        )

    async def mark_used(
        self, session: AsyncSession, token: EmailVerificationToken, at: datetime
    ) -> EmailVerificationToken:
        """Отмечает токен использованным."""
        return await self.update(session, token, {"used_at": at})


class RefreshSessionCRUD(CRUDBase[RefreshSession]):
    """Доступ к refresh-сессиям."""

    async def get_by_hash(self, session: AsyncSession, token_hash: str) -> RefreshSession | None:
        """Находит сессию по хешу refresh-токена с блокировкой строки.

        Два параллельных обновления одного токена (например, две вкладки) не должны
        оба получить новую пару: второе увидит отозванную сессию.
        """
        statement = (
            select(RefreshSession).where(RefreshSession.token_hash == token_hash).with_for_update()
        )
        return await session.scalar(statement)

    async def revoke(
        self,
        session: AsyncSession,
        refresh_session: RefreshSession,
        *,
        reason: SessionRevokeReason,
        at: datetime,
        replaced_by_id: uuid.UUID | None = None,
    ) -> RefreshSession:
        """Отзывает одну сессию."""
        return await self.update(
            session,
            refresh_session,
            {"revoked_at": at, "revoke_reason": reason, "replaced_by_id": replaced_by_id},
        )

    async def revoke_family(
        self,
        session: AsyncSession,
        family_id: uuid.UUID,
        *,
        reason: SessionRevokeReason,
        at: datetime,
    ) -> None:
        """Отзывает все ещё активные сессии семейства."""
        await session.execute(
            update(RefreshSession)
            .where(RefreshSession.family_id == family_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=at, revoke_reason=reason)
        )


email_verification_token_crud = EmailVerificationTokenCRUD(EmailVerificationToken)
refresh_session_crud = RefreshSessionCRUD(RefreshSession)
