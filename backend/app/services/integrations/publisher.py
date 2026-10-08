import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.crud import contact_disclosure_crud, webhook_delivery_crud, webhook_endpoint_crud
from app.models.integration import WebhookDelivery, WebhookEndpoint, WebhookEvent
from app.models.invitation import DeclineReason, Invitation
from app.models.vacancy import Application, Vacancy
from app.services.integrations.snapshot import CandidateSnapshotBuilder


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class WebhookPublisher:
    """Ставит события для ATS в outbox — в транзакции того сценария, где они случились.

    Сам ничего не отправляет и транзакцию не фиксирует: если принятие приглашения
    откатится, вместе с ним откатится и событие. Отправкой занимается диспетчер.
    Для компаний без подписчиков события не собираются вовсе — это один запрос.
    """

    def __init__(
        self, session: AsyncSession, settings: Settings, clock: Callable[[], datetime] = _now
    ) -> None:
        """Получает сессию БД, настройки и источник времени."""
        self._session = session
        self._clock = clock
        self._snapshots = CandidateSnapshotBuilder(session, settings.frontend_url, clock)

    async def invitation_accepted(self, invitation: Invitation) -> None:
        """Кандидат принял приглашение: в событии карточка с открытыми контактами."""
        endpoints = await self._subscribers(invitation.company_id, WebhookEvent.INVITATION_ACCEPTED)
        if not endpoints:
            return
        disclosure = await contact_disclosure_crud.get_for_pair(
            self._session, invitation.company_id, invitation.candidate_id
        )
        candidate = await self._snapshots.one(disclosure)
        await self._enqueue(
            endpoints,
            WebhookEvent.INVITATION_ACCEPTED,
            invitation.company_id,
            {
                "invitation": self._invitation(invitation),
                "candidate": candidate.model_dump(mode="json") if candidate else None,
            },
        )

    async def invitation_declined(
        self, invitation: Invitation, alias: str, reason: DeclineReason, comment: str
    ) -> None:
        """Кандидат отказался: причина для аналитики воронки, контактов нет."""
        endpoints = await self._subscribers(invitation.company_id, WebhookEvent.INVITATION_DECLINED)
        await self._enqueue(
            endpoints,
            WebhookEvent.INVITATION_DECLINED,
            invitation.company_id,
            {
                "invitation": self._invitation(invitation),
                "candidate": {"candidate_id": str(invitation.candidate_id), "alias": alias},
                "reason": reason.value,
                "comment": comment.strip(),
            },
        )

    async def application_created(self, application: Application, vacancy: Vacancy) -> None:
        """Новый отклик: кандидат сам открыл контакты, балл соответствия — в событии."""
        endpoints = await self._subscribers(vacancy.company_id, WebhookEvent.APPLICATION_CREATED)
        if not endpoints:
            return
        disclosure = await contact_disclosure_crud.get_for_pair(
            self._session, vacancy.company_id, application.candidate_id
        )
        candidate = await self._snapshots.one(disclosure)
        await self._enqueue(
            endpoints,
            WebhookEvent.APPLICATION_CREATED,
            vacancy.company_id,
            {
                "application": {
                    "id": str(application.id),
                    "match_score": application.match_score,
                    "cover_letter": application.cover_letter,
                },
                "vacancy": self._vacancy(vacancy),
                "candidate": candidate.model_dump(mode="json") if candidate else None,
            },
        )

    async def application_withdrawn(
        self, application: Application, vacancy: Vacancy, alias: str
    ) -> None:
        """Кандидат отозвал отклик — карточку в ATS стоит закрыть."""
        endpoints = await self._subscribers(vacancy.company_id, WebhookEvent.APPLICATION_WITHDRAWN)
        await self._enqueue(
            endpoints,
            WebhookEvent.APPLICATION_WITHDRAWN,
            vacancy.company_id,
            {
                "application": {"id": str(application.id)},
                "vacancy": self._vacancy(vacancy),
                "candidate": {"candidate_id": str(application.candidate_id), "alias": alias},
            },
        )

    async def ping(self, endpoint: WebhookEndpoint) -> WebhookDelivery:
        """Проверочное событие одному получателю — по кнопке в кабинете."""
        deliveries = await self._enqueue(
            [endpoint],
            WebhookEvent.PING,
            endpoint.company_id,
            {"message": "Проверка связи: «Скаут» подписывает события этим секретом"},
        )
        return deliveries[0]

    async def redeliver(self, delivery: WebhookDelivery) -> WebhookDelivery:
        """Повтор доставки отдельной записью с тем же `event_id`: получатель узнает дубль."""
        return await webhook_delivery_crud.create(
            self._session,
            {
                "endpoint_id": delivery.endpoint_id,
                "company_id": delivery.company_id,
                "event_id": delivery.event_id,
                "event_type": delivery.event_type,
                "payload": delivery.payload,
                "next_attempt_at": self._clock(),
            },
        )

    async def _subscribers(
        self, company_id: uuid.UUID, event: WebhookEvent
    ) -> Sequence[WebhookEndpoint]:
        """Активные получатели компании, подписанные на событие."""
        return await webhook_endpoint_crud.subscribed(self._session, company_id, event.value)

    async def _enqueue(
        self,
        endpoints: Sequence[WebhookEndpoint],
        event: WebhookEvent,
        company_id: uuid.UUID,
        data: dict[str, Any],
    ) -> list[WebhookDelivery]:
        """Одна запись outbox на получателя; у всех один `event_id` и одинаковое тело."""
        if not endpoints:
            return []
        now = self._clock()
        event_id = uuid.uuid4()
        payload = {
            "id": str(event_id),
            "type": event.value,
            "created_at": now.isoformat(),
            "company_id": str(company_id),
            "data": data,
        }
        return [
            await webhook_delivery_crud.create(
                self._session,
                {
                    "endpoint_id": endpoint.id,
                    "company_id": company_id,
                    "event_id": event_id,
                    "event_type": event.value,
                    "payload": payload,
                    "next_attempt_at": now,
                },
            )
            for endpoint in endpoints
        ]

    @staticmethod
    def _invitation(invitation: Invitation) -> dict[str, Any]:
        """Приглашение в событии: условия, с которыми компания приглашала."""
        return {
            "id": str(invitation.id),
            "title": invitation.title,
            "need_id": str(invitation.need_id) if invitation.need_id else None,
            "salary_from": invitation.salary_from,
            "salary_to": invitation.salary_to,
            "salary_gross": invitation.salary_gross,
            "work_format": invitation.work_format.value,
            "status": invitation.status.value,
        }

    @staticmethod
    def _vacancy(vacancy: Vacancy) -> dict[str, Any]:
        """Вакансия в событии."""
        return {"id": str(vacancy.id), "title": vacancy.title}
