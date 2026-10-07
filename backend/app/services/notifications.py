import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.crud import notification_crud
from app.models.notification import Notification, NotificationKind
from app.models.user import User
from app.schemas.notification import NotificationListRead, NotificationRead


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def _read(notification: Notification) -> NotificationRead:
    """Уведомление для ответа API."""
    payload = notification.payload
    return NotificationRead(
        id=notification.id,
        kind=notification.kind,
        title=str(payload.get("title", "")),
        text=str(payload.get("text", "")),
        link=payload.get("link"),
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


class NotificationService:
    """Уведомления в кабинете: создание из сценариев и чтение пользователем."""

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._clock = clock

    async def notify(
        self,
        user_id: uuid.UUID,
        kind: NotificationKind,
        *,
        title: str,
        text: str,
        link: str | None = None,
    ) -> None:
        """Создаёт уведомление. Транзакцию фиксирует вызывающий сценарий."""
        await notification_crud.create(
            self._session,
            {
                "user_id": user_id,
                "kind": kind,
                "payload": {"title": title, "text": text, "link": link},
            },
        )

    async def list(self, user: User) -> NotificationListRead:
        """Последние уведомления и число непрочитанных."""
        items = await notification_crud.list_for_user(self._session, user.id)
        unread = await notification_crud.unread_count(self._session, user.id)
        return NotificationListRead(items=[_read(item) for item in items], unread=unread)

    async def mark_read(
        self, user: User, notification_id: uuid.UUID | None = None
    ) -> NotificationListRead:
        """Отмечает прочитанным одно уведомление или все сразу."""
        changed = await notification_crud.mark_read(
            self._session, user.id, self._clock(), notification_id
        )
        if notification_id is not None and changed == 0:
            existing = await notification_crud.get(self._session, notification_id)
            if existing is None or existing.user_id != user.id:
                raise NotFoundError("Уведомление не найдено")
        await self._session.commit()
        return await self.list(user)
