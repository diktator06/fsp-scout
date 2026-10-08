import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.integration import DeliveryStatus, WebhookDelivery, WebhookEndpoint


class WebhookEndpointCRUD(CRUDBase[WebhookEndpoint]):
    """Доступ к получателям вебхуков."""

    async def list_for_company(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> Sequence[WebhookEndpoint]:
        """Получатели компании в порядке подключения."""
        result = await session.scalars(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.company_id == company_id)
            .order_by(WebhookEndpoint.created_at)
        )
        return result.all()

    async def get_for_company(
        self, session: AsyncSession, endpoint_id: uuid.UUID, company_id: uuid.UUID
    ) -> WebhookEndpoint | None:
        """Получатель, если он принадлежит компании."""
        return await session.scalar(
            select(WebhookEndpoint).where(
                WebhookEndpoint.id == endpoint_id, WebhookEndpoint.company_id == company_id
            )
        )

    async def count_for_company(self, session: AsyncSession, company_id: uuid.UUID) -> int:
        """Сколько получателей подключено у компании."""
        total = await session.scalar(
            select(func.count())
            .select_from(WebhookEndpoint)
            .where(WebhookEndpoint.company_id == company_id)
        )
        return int(total or 0)

    async def subscribed(
        self, session: AsyncSession, company_id: uuid.UUID, event: str
    ) -> Sequence[WebhookEndpoint]:
        """Активные получатели компании, подписанные на событие."""
        result = await session.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.company_id == company_id,
                WebhookEndpoint.is_active.is_(True),
                WebhookEndpoint.events.contains([event]),
            )
        )
        return result.all()

    async def by_ids(
        self, session: AsyncSession, endpoint_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, WebhookEndpoint]:
        """Получатели по идентификаторам."""
        if not endpoint_ids:
            return {}
        result = await session.scalars(
            select(WebhookEndpoint).where(WebhookEndpoint.id.in_(endpoint_ids))
        )
        return {item.id: item for item in result.all()}


class WebhookDeliveryCRUD(CRUDBase[WebhookDelivery]):
    """Доступ к журналу доставок (outbox)."""

    async def lock_due(
        self, session: AsyncSession, now: datetime, limit: int
    ) -> Sequence[WebhookDelivery]:
        """Доставки, которым пора уходить, с блокировкой строк.

        `SKIP LOCKED` позволяет нескольким процессам разбирать очередь одновременно:
        строку, которую уже взял другой процесс, этот просто пропускает.
        """
        result = await session.scalars(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.status == DeliveryStatus.PENDING,
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return result.all()

    async def list_for_company(
        self, session: AsyncSession, company_id: uuid.UUID, *, limit: int
    ) -> Sequence[WebhookDelivery]:
        """Последние доставки компании, новые сверху."""
        result = await session.scalars(
            select(WebhookDelivery)
            .where(WebhookDelivery.company_id == company_id)
            .order_by(WebhookDelivery.created_at.desc())
            .limit(limit)
        )
        return result.all()

    async def get_for_company(
        self, session: AsyncSession, delivery_id: uuid.UUID, company_id: uuid.UUID
    ) -> WebhookDelivery | None:
        """Доставка, если она принадлежит компании."""
        return await session.scalar(
            select(WebhookDelivery).where(
                WebhookDelivery.id == delivery_id, WebhookDelivery.company_id == company_id
            )
        )


webhook_endpoint_crud = WebhookEndpointCRUD(WebhookEndpoint)
webhook_delivery_crud = WebhookDeliveryCRUD(WebhookDelivery)
