import uuid
from collections.abc import Sequence

from sqlalchemy import select
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


consent_crud = ConsentCRUD(Consent)
