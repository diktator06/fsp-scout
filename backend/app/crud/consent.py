import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.consent import Consent, ConsentType


class ConsentCRUD(CRUDBase[Consent]):
    """Доступ к журналу согласий."""

    async def grant(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        consent_type: ConsentType,
        document_version: str,
        ip_address: str | None,
    ) -> Consent:
        """Записывает выданное согласие."""
        return await self.create(
            session,
            {
                "user_id": user_id,
                "consent_type": consent_type,
                "document_version": document_version,
                "ip_address": ip_address,
            },
        )

    async def list_for_user(self, session: AsyncSession, user_id: uuid.UUID) -> Sequence[Consent]:
        """Все согласия пользователя, от новых к старым."""
        result = await session.scalars(
            select(Consent).where(Consent.user_id == user_id).order_by(Consent.granted_at.desc())
        )
        return result.all()

    async def active(
        self, session: AsyncSession, user_id: uuid.UUID, consent_type: ConsentType
    ) -> Consent | None:
        """Действующее (не отозванное) согласие указанного вида."""
        return await session.scalar(
            select(Consent)
            .where(
                Consent.user_id == user_id,
                Consent.consent_type == consent_type,
                Consent.revoked_at.is_(None),
            )
            .order_by(Consent.granted_at.desc())
            .limit(1)
        )

    async def revoke_active(
        self, session: AsyncSession, user_id: uuid.UUID, consent_type: ConsentType, at: datetime
    ) -> None:
        """Отзывает действующие согласия вида; записи остаются в журнале с датой отзыва."""
        await session.execute(
            update(Consent)
            .where(
                Consent.user_id == user_id,
                Consent.consent_type == consent_type,
                Consent.revoked_at.is_(None),
            )
            .values(revoked_at=at)
        )


consent_crud = ConsentCRUD(Consent)
