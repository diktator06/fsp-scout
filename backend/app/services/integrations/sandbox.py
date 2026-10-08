import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import NotFoundError, WebhookSignatureError
from app.crud import webhook_delivery_crud, webhook_endpoint_crud
from app.models.integration import WebhookEvent
from app.schemas.integration import SandboxReceipt
from app.services.integrations import signing
from app.services.integrations.dispatcher import is_sandbox


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class SandboxReceiver:
    """Встроенная песочница ATS: принимает вебхуки и проверяет подпись, как это делала бы ATS.

    Нужна, чтобы интеграцию можно было показать без внешнего сервиса: работодатель
    подключает песочницу одной кнопкой и видит в журнале доставок её ответ. Секрет
    песочница находит по заголовку доставки — у настоящей ATS он хранится у себя.
    """

    def __init__(
        self, session: AsyncSession, settings: Settings, clock: Callable[[], datetime] = _now
    ) -> None:
        """Получает сессию БД, настройки и источник времени."""
        self._session = session
        self._settings = settings
        self._clock = clock

    async def receive(self, headers: Mapping[str, str], body: bytes) -> SandboxReceipt:
        """Проверяет подпись и возвращает квитанцию, как ответила бы ATS."""
        try:
            delivery_id = uuid.UUID(headers.get(signing.DELIVERY_HEADER, ""))
        except ValueError as error:
            raise NotFoundError("Доставка не найдена") from error
        delivery = await webhook_delivery_crud.get(self._session, delivery_id)
        endpoint = (
            await webhook_endpoint_crud.get(self._session, delivery.endpoint_id)
            if delivery
            else None
        )
        if delivery is None or endpoint is None or not is_sandbox(endpoint.url, self._settings):
            raise NotFoundError("Доставка не найдена")
        valid = signing.verify(
            endpoint.secret,
            headers.get(signing.TIMESTAMP_HEADER, ""),
            body,
            headers.get(signing.SIGNATURE_HEADER, ""),
            int(self._clock().timestamp()),
        )
        if not valid:
            raise WebhookSignatureError()
        return SandboxReceipt(
            received=True,
            signature_valid=True,
            event_type=delivery.event_type,
            event_id=delivery.event_id,
            message=self._message(delivery.event_type, delivery.payload.get("data", {})),
        )

    @staticmethod
    def _message(event_type: str, data: dict[str, object]) -> str:
        """Что «сделала» ATS с событием — для журнала доставок в кабинете."""
        candidate = data.get("candidate")
        name = candidate.get("full_name") if isinstance(candidate, dict) else None
        messages = {
            WebhookEvent.INVITATION_ACCEPTED.value: f"Карточка кандидата «{name}» заведена",
            WebhookEvent.APPLICATION_CREATED.value: f"Отклик кандидата «{name}» добавлен в воронку",
            WebhookEvent.INVITATION_DECLINED.value: "Отказ записан в аналитику воронки",
            WebhookEvent.APPLICATION_WITHDRAWN.value: "Карточка кандидата закрыта",
            WebhookEvent.PING.value: "Связь установлена, подпись верна",
        }
        return "Песочница ATS: " + messages.get(event_type, "событие принято")
