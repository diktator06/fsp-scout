import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.notification import Notification


class NotificationCRUD(CRUDBase[Notification]):
    """Доступ к уведомлениям."""

    async def list_for_user(
        self, session: AsyncSession, user_id: uuid.UUID, *, limit: int = 30
    ) -> Sequence[Notification]:
        """Последние уведомления пользователя."""
        result = await session.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return result.all()

    async def unread_count(self, session: AsyncSession, user_id: uuid.UUID) -> int:
        """Сколько непрочитанных уведомлений у пользователя."""
        total = await session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        return int(total or 0)

    async def mark_read(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        at: datetime,
        notification_id: uuid.UUID | None = None,
    ) -> int:
        """Отмечает прочитанным одно уведомление пользователя или все сразу."""
        statement = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=at)
        )
        if notification_id is not None:
            statement = statement.where(Notification.id == notification_id)
        result = await session.execute(statement)
        return int(getattr(result, "rowcount", 0) or 0)


notification_crud = NotificationCRUD(Notification)
