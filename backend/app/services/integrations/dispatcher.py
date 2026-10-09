import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import UnsafeWebhookUrlError
from app.crud import recruiter_crud, webhook_delivery_crud, webhook_endpoint_crud
from app.models.integration import DeliveryStatus
from app.models.notification import NotificationKind
from app.services.integrations import signing
from app.services.integrations.url_guard import ensure_public_destination
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)

RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=6),
)
MAX_ATTEMPTS = len(RETRY_DELAYS) + 1
LEASE = timedelta(minutes=2)
BATCH_SIZE = 20
RESPONSE_PREVIEW = 500
USER_AGENT = "Scout-Webhooks/1.0"

type SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def is_sandbox(url: str, settings: Settings) -> bool:
    """Получатель — встроенная песочница ATS: её адрес внутренний по определению."""
    return url == settings.webhook_sandbox_url


@dataclass(frozen=True, slots=True)
class _Job:
    """Снимок доставки для отправки вне транзакции."""

    delivery_id: uuid.UUID
    company_id: uuid.UUID
    event_id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    url: str
    secret: str
    active: bool


@dataclass(frozen=True, slots=True)
class _Outcome:
    """Итог одной попытки."""

    ok: bool
    status_code: int | None = None
    body: str = ""
    error: str = ""
    final: bool = False


class WebhookDispatcher:
    """Фоновая доставка событий из outbox с повторами.

    Попытка устроена в три шага: короткой транзакцией строки берутся с блокировкой
    `SKIP LOCKED` и «арендуются» на две минуты; запрос уходит уже вне транзакции;
    результат записывается второй короткой транзакцией. Если процесс упадёт посреди
    отправки, аренда истечёт и доставка повторится — получатель отличит дубль по
    `event_id`. Неудачи повторяются через 1, 5, 30 минут, 2 и 6 часов; после шестой
    попытки доставка помечается неудачной, а рекрутеры получают уведомление.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        """Получает фабрику сессий, настройки, HTTP-транспорт (для тестов) и время."""
        self._session_factory = session_factory
        self._settings = settings
        self._transport = transport
        self._clock = clock

    async def run_forever(self, stop: asyncio.Event) -> None:
        """Цикл диспетчера до сигнала остановки; сбой одной итерации цикл не роняет."""
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("Сбой итерации доставки вебхуков")
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=self._settings.webhook_dispatch_interval_seconds
                )
            except TimeoutError:
                continue

    async def run_once(self) -> int:
        """Одна итерация: забрать созревшие доставки, отправить, записать итог."""
        jobs = await self._claim()
        if not jobs:
            return 0
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=self._settings.webhook_timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            outcomes = await asyncio.gather(*(self._send(client, job) for job in jobs))
        await self._record(list(zip(jobs, outcomes, strict=True)))
        return len(jobs)

    async def _claim(self) -> list[_Job]:
        """Берёт пачку доставок в аренду и сразу фиксирует это."""
        now = self._clock()
        async with self._session_factory() as session:
            due = await webhook_delivery_crud.lock_due(session, now, BATCH_SIZE)
            if not due:
                return []
            endpoints = await webhook_endpoint_crud.by_ids(
                session, list({item.endpoint_id for item in due})
            )
            jobs = []
            for delivery in due:
                endpoint = endpoints[delivery.endpoint_id]
                await webhook_delivery_crud.update(
                    session,
                    delivery,
                    {
                        "attempts": delivery.attempts + 1,
                        "last_attempt_at": now,
                        "next_attempt_at": now + LEASE,
                    },
                )
                jobs.append(
                    _Job(
                        delivery_id=delivery.id,
                        company_id=delivery.company_id,
                        event_id=delivery.event_id,
                        event_type=delivery.event_type,
                        payload=delivery.payload,
                        url=endpoint.url,
                        secret=endpoint.secret,
                        active=endpoint.is_active,
                    )
                )
            await session.commit()
        return jobs

    async def _send(self, client: httpx.AsyncClient, job: _Job) -> _Outcome:
        """Подписанный POST получателю. Перенаправления не выполняются: это обход проверки."""
        if not job.active:
            return _Outcome(ok=False, error="Получатель отключён в кабинете", final=True)
        body = signing.encode_payload(job.payload)
        timestamp = int(self._clock().timestamp())
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            signing.EVENT_HEADER: job.event_type,
            signing.EVENT_ID_HEADER: str(job.event_id),
            signing.DELIVERY_HEADER: str(job.delivery_id),
            signing.TIMESTAMP_HEADER: str(timestamp),
            signing.SIGNATURE_HEADER: signing.sign(job.secret, timestamp, body),
        }
        try:
            if not is_sandbox(job.url, self._settings):
                await ensure_public_destination(
                    job.url,
                    allow_private=self._settings.webhook_allow_private_urls,
                    require_https=self._settings.is_production,
                )
            response = await client.post(job.url, content=body, headers=headers)
        except UnsafeWebhookUrlError as error:
            return _Outcome(ok=False, error=error.message, final=True)
        except httpx.TimeoutException:
            return _Outcome(ok=False, error="Получатель не ответил вовремя")
        except httpx.HTTPError as error:
            return _Outcome(ok=False, error=f"Ошибка соединения: {type(error).__name__}")
        return _Outcome(
            ok=response.is_success,
            status_code=response.status_code,
            body=response.text[:RESPONSE_PREVIEW],
            error="" if response.is_success else f"Получатель ответил {response.status_code}",
        )

    async def _record(self, results: list[tuple[_Job, _Outcome]]) -> None:
        """Записывает итоги попыток и сообщает рекрутерам о доставках, которые не удались."""
        now = self._clock()
        async with self._session_factory() as session:
            notifications = NotificationService(session, self._clock)
            for job, outcome in results:
                delivery = await webhook_delivery_crud.get(session, job.delivery_id)
                if delivery is None:
                    continue
                changes: dict[str, Any] = {
                    "response_status": outcome.status_code,
                    "response_body": outcome.body,
                    "error": outcome.error[:300],
                }
                if outcome.ok:
                    changes |= {"status": DeliveryStatus.DELIVERED, "delivered_at": now}
                elif outcome.final or delivery.attempts >= MAX_ATTEMPTS:
                    changes["status"] = DeliveryStatus.FAILED
                else:
                    changes["next_attempt_at"] = now + RETRY_DELAYS[delivery.attempts - 1]
                await webhook_delivery_crud.update(session, delivery, changes)
                if delivery.status is DeliveryStatus.FAILED:
                    for user_id in await recruiter_crud.user_ids_for_company(
                        session, job.company_id
                    ):
                        await notifications.notify(
                            user_id,
                            NotificationKind.WEBHOOK_FAILED,
                            title="ATS не приняла событие",
                            text=f"{job.event_type}: {delivery.error}",
                            link="/e/integrations",
                        )
            await session.commit()
