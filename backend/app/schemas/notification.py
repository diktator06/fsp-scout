import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.notification import NotificationKind


class NotificationRead(BaseModel):
    """Уведомление в кабинете."""

    id: uuid.UUID
    kind: NotificationKind
    title: str
    text: str
    link: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationListRead(BaseModel):
    """Последние уведомления и число непрочитанных."""

    items: list[NotificationRead]
    unread: int
