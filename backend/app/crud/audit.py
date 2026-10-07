import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.audit import AuditLog


class AuditLogCRUD(CRUDBase[AuditLog]):
    """Доступ к журналу аудита."""

    async def record(
        self,
        session: AsyncSession,
        *,
        actor_user_id: uuid.UUID | None,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | str,
        meta: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        """Записывает событие аудита."""
        return await self.create(
            session,
            {
                "actor_user_id": actor_user_id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "meta": dict(meta or {}),
            },
        )


audit_log_crud = AuditLogCRUD(AuditLog)
