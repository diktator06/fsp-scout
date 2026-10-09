import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.crud import (
    audit_log_crud,
    contact_disclosure_crud,
    webhook_delivery_crud,
    webhook_endpoint_crud,
)
from app.models.integration import DeliveryStatus, WebhookDelivery, WebhookEndpoint
from app.models.user import User
from app.schemas.integration import (
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointRead,
    WebhookEndpointSecretRead,
    WebhookEndpointUpdate,
    WebhookEventInfo,
)
from app.services.employer.company_service import CompanyService
from app.services.integrations import signing
from app.services.integrations.catalog import EVENT_CATALOG, SUBSCRIBABLE_EVENTS
from app.services.integrations.dispatcher import MAX_ATTEMPTS, is_sandbox
from app.services.integrations.export import ExportFile, ExportFormat, render
from app.services.integrations.publisher import WebhookPublisher
from app.services.integrations.snapshot import CandidateSnapshotBuilder
from app.services.integrations.url_guard import ensure_public_destination

DELIVERY_LOG_LIMIT = 50


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class IntegrationService:
    """Интеграция с ATS работодателя: вебхуки, журнал доставок и выгрузка кандидатов.

    Платформа не заменяет ATS компании, а встраивается в неё: события о кандидатах
    уходят подписанными вебхуками, а всех, кто открыл компании контакты, можно
    выгрузить файлом. В обоих случаях наружу попадает только раскрытое кандидатом.
    """

    def __init__(
        self, session: AsyncSession, settings: Settings, clock: Callable[[], datetime] = _now
    ) -> None:
        """Получает сессию БД, настройки и источник времени."""
        self._session = session
        self._settings = settings
        self._clock = clock
        self._companies = CompanyService(session, clock)
        self._publisher = WebhookPublisher(session, settings, clock)

    @staticmethod
    def events() -> list[WebhookEventInfo]:
        """Каталог событий, на которые можно подписаться."""
        return list(EVENT_CATALOG)

    async def endpoints(self, user: User) -> list[WebhookEndpointRead]:
        """Получатели компании."""
        recruiter = await self._companies.require_recruiter(user)
        items = await webhook_endpoint_crud.list_for_company(self._session, recruiter.company_id)
        return [self._endpoint_read(item) for item in items]

    async def create_endpoint(
        self, user: User, payload: WebhookEndpointCreate
    ) -> WebhookEndpointSecretRead:
        """Подключает адрес ATS. Секрет показывается полностью только в этом ответе."""
        recruiter = await self._companies.require_recruiter(user)
        url = str(payload.url)
        if not is_sandbox(url, self._settings):
            await ensure_public_destination(
                url,
                allow_private=self._settings.webhook_allow_private_urls,
                require_https=self._settings.is_production,
            )
        endpoint = await self._create(
            user,
            recruiter.company_id,
            url,
            [item.value for item in payload.events],
            payload.description.strip(),
        )
        await self._session.commit()
        return self._secret_read(endpoint)

    async def connect_sandbox(self, user: User) -> WebhookEndpointSecretRead:
        """Подключает встроенную песочницу ATS на все события — для проверки без своей ATS."""
        recruiter = await self._companies.require_recruiter(user)
        existing = await webhook_endpoint_crud.list_for_company(self._session, recruiter.company_id)
        if any(is_sandbox(item.url, self._settings) for item in existing):
            raise ConflictError("Песочница уже подключена")
        endpoint = await self._create(
            user,
            recruiter.company_id,
            self._settings.webhook_sandbox_url,
            [item.value for item in SUBSCRIBABLE_EVENTS],
            "Песочница ATS «Скаута»",
        )
        await self._session.commit()
        return self._secret_read(endpoint)

    async def update_endpoint(
        self, user: User, endpoint_id: uuid.UUID, payload: WebhookEndpointUpdate
    ) -> WebhookEndpointRead:
        """Меняет подписку, описание или включает и отключает получателя."""
        endpoint = await self._own(user, endpoint_id)
        changes: dict[str, Any] = {}
        if payload.events is not None:
            changes["events"] = [item.value for item in payload.events]
        if payload.description is not None:
            changes["description"] = payload.description.strip()
        if payload.is_active is not None:
            changes["is_active"] = payload.is_active
        await webhook_endpoint_crud.update(self._session, endpoint, changes)
        await self._session.commit()
        return self._endpoint_read(endpoint)

    async def rotate_secret(self, user: User, endpoint_id: uuid.UUID) -> WebhookEndpointSecretRead:
        """Новый секрет: старый перестаёт подходить к подписи сразу."""
        endpoint = await self._own(user, endpoint_id)
        await webhook_endpoint_crud.update(
            self._session, endpoint, {"secret": signing.new_secret()}
        )
        await self._audit(user, "webhook_secret_rotated", endpoint)
        await self._session.commit()
        return self._secret_read(endpoint)

    async def delete_endpoint(self, user: User, endpoint_id: uuid.UUID) -> None:
        """Отключает получателя насовсем вместе с журналом его доставок."""
        endpoint = await self._own(user, endpoint_id)
        await self._audit(user, "webhook_endpoint_deleted", endpoint)
        await webhook_endpoint_crud.delete(self._session, endpoint)
        await self._session.commit()

    async def test_endpoint(self, user: User, endpoint_id: uuid.UUID) -> WebhookDeliveryRead:
        """Проверочное событие `ping` — уйдёт с ближайшей итерацией диспетчера."""
        endpoint = await self._own(user, endpoint_id)
        if not endpoint.is_active:
            raise ConflictError("Получатель отключён — включите его, чтобы проверить связь")
        delivery = await self._publisher.ping(endpoint)
        await self._session.commit()
        return self._delivery_read(delivery, endpoint)

    async def deliveries(self, user: User) -> list[WebhookDeliveryRead]:
        """Журнал последних доставок компании."""
        recruiter = await self._companies.require_recruiter(user)
        items = await webhook_delivery_crud.list_for_company(
            self._session, recruiter.company_id, limit=DELIVERY_LOG_LIMIT
        )
        endpoints = await webhook_endpoint_crud.by_ids(
            self._session, list({item.endpoint_id for item in items})
        )
        return [self._delivery_read(item, endpoints[item.endpoint_id]) for item in items]

    async def redeliver(self, user: User, delivery_id: uuid.UUID) -> WebhookDeliveryRead:
        """Повтор неудавшейся доставки — например, после того как ATS починили."""
        recruiter = await self._companies.require_recruiter(user)
        delivery = await webhook_delivery_crud.get_for_company(
            self._session, delivery_id, recruiter.company_id
        )
        if delivery is None:
            raise NotFoundError("Доставка не найдена")
        if delivery.status is not DeliveryStatus.FAILED:
            raise ConflictError("Повторить можно только неудавшуюся доставку")
        endpoint = await webhook_endpoint_crud.get(self._session, delivery.endpoint_id)
        assert endpoint is not None
        if not endpoint.is_active:
            raise ConflictError("Получатель отключён — включите его, чтобы повторить доставку")
        copy = await self._publisher.redeliver(delivery)
        await self._session.commit()
        return self._delivery_read(copy, endpoint)

    async def export(self, user: User, fmt: ExportFormat) -> ExportFile:
        """Выгрузка всех, кто открыл компании контакты. Каждая выгрузка пишется в аудит."""
        recruiter = await self._companies.require_recruiter(user)
        disclosures = await contact_disclosure_crud.list_for_company(
            self._session, recruiter.company_id
        )
        builder = CandidateSnapshotBuilder(self._session, self._settings.frontend_url, self._clock)
        candidates = await builder.build(disclosures)
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action="candidates_exported",
            entity_type="company",
            entity_id=recruiter.company_id,
            meta={"format": fmt, "count": len(candidates)},
        )
        await self._session.commit()
        return render(candidates, fmt, self._clock())

    async def _create(
        self,
        user: User,
        company_id: uuid.UUID,
        url: str,
        events: list[str],
        description: str,
    ) -> WebhookEndpoint:
        """Создаёт получателя в пределах лимита компании."""
        count = await webhook_endpoint_crud.count_for_company(self._session, company_id)
        if count >= self._settings.webhook_endpoints_per_company:
            raise ConflictError(
                f"Подключено максимум получателей: {self._settings.webhook_endpoints_per_company}"
            )
        endpoint = await webhook_endpoint_crud.create(
            self._session,
            {
                "company_id": company_id,
                "url": url,
                "secret": signing.new_secret(),
                "events": events,
                "description": description,
                "created_by": user.id,
            },
        )
        await self._audit(user, "webhook_endpoint_created", endpoint)
        return endpoint

    async def _own(self, user: User, endpoint_id: uuid.UUID) -> WebhookEndpoint:
        """Получатель компании пользователя или 404."""
        recruiter = await self._companies.require_recruiter(user)
        endpoint = await webhook_endpoint_crud.get_for_company(
            self._session, endpoint_id, recruiter.company_id
        )
        if endpoint is None:
            raise NotFoundError("Получатель не найден")
        return endpoint

    async def _audit(self, user: User, action: str, endpoint: WebhookEndpoint) -> None:
        """Изменения интеграций — в журнал аудита: через них уходят персональные данные."""
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action=action,
            entity_type="webhook_endpoint",
            entity_id=endpoint.id,
            meta={"company_id": str(endpoint.company_id), "url": endpoint.url},
        )

    def _endpoint_read(self, endpoint: WebhookEndpoint) -> WebhookEndpointRead:
        """Получатель для ответа API — без секрета."""
        return WebhookEndpointRead(
            id=endpoint.id,
            url=endpoint.url,
            events=endpoint.events,
            description=endpoint.description,
            is_active=endpoint.is_active,
            is_sandbox=is_sandbox(endpoint.url, self._settings),
            secret_hint=signing.secret_hint(endpoint.secret),
            created_at=endpoint.created_at,
        )

    def _secret_read(self, endpoint: WebhookEndpoint) -> WebhookEndpointSecretRead:
        """Получатель с полным секретом."""
        return WebhookEndpointSecretRead(
            **self._endpoint_read(endpoint).model_dump(), secret=endpoint.secret
        )

    @staticmethod
    def _delivery_read(delivery: WebhookDelivery, endpoint: WebhookEndpoint) -> WebhookDeliveryRead:
        """Доставка для журнала."""
        pending = delivery.status is DeliveryStatus.PENDING
        return WebhookDeliveryRead(
            id=delivery.id,
            endpoint_id=delivery.endpoint_id,
            endpoint_url=endpoint.url,
            event_id=delivery.event_id,
            event_type=delivery.event_type,
            status=delivery.status,
            attempts=delivery.attempts,
            max_attempts=MAX_ATTEMPTS,
            next_attempt_at=delivery.next_attempt_at if pending else None,
            last_attempt_at=delivery.last_attempt_at,
            response_status=delivery.response_status,
            response_body=delivery.response_body,
            error=delivery.error,
            delivered_at=delivery.delivered_at,
            created_at=delivery.created_at,
            payload=delivery.payload,
        )
