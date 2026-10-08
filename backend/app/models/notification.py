import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum


class NotificationKind(StrEnum):
    """Виды уведомлений в кабинете."""

    INVITATION_RECEIVED = "invitation_received"
    INVITATION_ACCEPTED = "invitation_accepted"
    INVITATION_DECLINED = "invitation_declined"
    INVITATION_WITHDRAWN = "invitation_withdrawn"
    INVITATION_EXPIRED = "invitation_expired"
    APPLICATION_RECEIVED = "application_received"
    APPLICATION_UPDATED = "application_updated"
    MICROTASK_SUBMITTED = "microtask_submitted"
    MICROTASK_GRADED = "microtask_graded"
    COMPANY_RESTRICTED = "company_restricted"
    WEBHOOK_FAILED = "webhook_failed"


class Notification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Уведомление пользователю. В `payload` — заголовок, текст и ссылка внутри кабинета."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[NotificationKind] = mapped_column(pg_enum(NotificationKind, "notification_kind"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    read_at: Mapped[datetime | None]
