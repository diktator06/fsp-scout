import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum


class WebhookEvent(StrEnum):
    """События, о которых платформа сообщает ATS работодателя."""

    INVITATION_ACCEPTED = "invitation.accepted"
    INVITATION_DECLINED = "invitation.declined"
    APPLICATION_CREATED = "application.created"
    APPLICATION_WITHDRAWN = "application.withdrawn"
    PING = "ping"


class DeliveryStatus(StrEnum):
    """Состояние доставки события получателю."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class WebhookEndpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Адрес ATS работодателя, куда платформа отправляет события.

    Секрет нужен получателю, чтобы проверить подпись HMAC-SHA256: так ATS отличает
    настоящие события «Скаута» от подделки. Хранится в открытом виде, потому что
    подписывать без него нельзя; наружу отдаётся полностью только при создании и
    смене.
    """

    __tablename__ = "webhook_endpoints"
    __table_args__ = (Index("ix_webhook_endpoints_company_id", "company_id"),)

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[str] = mapped_column(String(80))
    events: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), default=list, server_default=text("'{}'::varchar[]")
    )
    description: Mapped[str] = mapped_column(String(200), default="", server_default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class WebhookDelivery(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Доставка одного события одному получателю — запись outbox.

    Создаётся в той же транзакции, что и само событие (принятие приглашения, отклик):
    если транзакция откатилась, события не было и отправлять нечего. Отправляет
    фоновый диспетчер с повторами; `event_id` одинаков у всех доставок события и
    служит получателю ключом идемпотентности.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_webhook_deliveries_due", "status", "next_attempt_at"),
        Index("ix_webhook_deliveries_company_created", "company_id", "created_at"),
    )

    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="CASCADE")
    )
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    event_id: Mapped[uuid.UUID]
    event_type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[DeliveryStatus] = mapped_column(
        pg_enum(DeliveryStatus, "webhook_delivery_status"),
        default=DeliveryStatus.PENDING,
        server_default=DeliveryStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime]
    last_attempt_at: Mapped[datetime | None]
    response_status: Mapped[int | None]
    response_body: Mapped[str] = mapped_column(String(500), default="", server_default="")
    error: Mapped[str] = mapped_column(String(300), default="", server_default="")
    delivered_at: Mapped[datetime | None]
