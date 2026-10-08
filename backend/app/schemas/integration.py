import uuid
from datetime import datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator

from app.models.integration import DeliveryStatus, WebhookEvent
from app.models.invitation import DisclosureReason


class AtsCandidate(BaseModel):
    """Кандидат в формате для ATS: только то, что он сам открыл компании."""

    candidate_id: uuid.UUID
    alias: str
    full_name: str | None
    email: str | None
    phone: str | None
    telegram: str | None
    city: str | None
    specialization: str
    grade: str
    category: str
    grade_confirmed: bool = Field(description="Грейд подтверждён тестом на платформе")
    verified_score: float = Field(description="Индекс подтверждённого профиля, 0–100")
    experience_years: float | None
    skills: list[str]
    profile_url: str
    source: DisclosureReason = Field(description="Почему компании открыты контакты")
    source_id: uuid.UUID | None = Field(description="Приглашение или отклик, открывший контакты")
    disclosed_at: datetime


class WebhookEventInfo(BaseModel):
    """Описание события для каталога."""

    type: WebhookEvent
    title: str
    description: str
    contains_contacts: bool


def subscribable_events(value: list[WebhookEvent]) -> list[WebhookEvent]:
    """События подписки без повторов. Проверочное отправляется по кнопке, в подписке его нет."""
    events: list[WebhookEvent] = []
    for item in value:
        if item is not WebhookEvent.PING and item not in events:
            events.append(item)
    if not events:
        raise ValueError("Выберите хотя бы одно событие")
    return events


class WebhookEndpointCreate(BaseModel):
    """Подключение ATS: адрес и события, на которые компания подписывается."""

    url: AnyHttpUrl
    events: list[WebhookEvent] = Field(min_length=1)
    description: str = Field(default="", max_length=200)

    @field_validator("url")
    @classmethod
    def limit_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        """Длина адреса ограничена колонкой в базе; данные для входа в адресе запрещены."""
        if len(str(value)) > 500:
            raise ValueError("Адрес длиннее 500 символов")
        if value.username or value.password:
            raise ValueError("Не передавайте логин и пароль в адресе — используйте подпись")
        return value

    @field_validator("events")
    @classmethod
    def drop_ping(cls, value: list[WebhookEvent]) -> list[WebhookEvent]:
        """Проверочное событие отправляется по кнопке, подписываться на него не нужно."""
        return subscribable_events(value)


class WebhookEndpointUpdate(BaseModel):
    """Изменение подписки: события, описание, включение и отключение."""

    events: list[WebhookEvent] | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None

    @field_validator("events")
    @classmethod
    def drop_ping(cls, value: list[WebhookEvent] | None) -> list[WebhookEvent] | None:
        """Как при создании: проверочное событие в подписке не хранится."""
        return None if value is None else subscribable_events(value)


class WebhookEndpointRead(BaseModel):
    """Получатель вебхуков. Секрет показывается подсказкой: первые и последние символы."""

    id: uuid.UUID
    url: str
    events: list[WebhookEvent]
    description: str
    is_active: bool
    is_sandbox: bool
    secret_hint: str
    created_at: datetime


class WebhookEndpointSecretRead(WebhookEndpointRead):
    """Получатель с полным секретом — только сразу после создания или смены секрета."""

    secret: str


class WebhookDeliveryRead(BaseModel):
    """Доставка события: статус, попытки и ответ получателя."""

    id: uuid.UUID
    endpoint_id: uuid.UUID
    endpoint_url: str
    event_id: uuid.UUID
    event_type: str
    status: DeliveryStatus
    attempts: int
    max_attempts: int
    next_attempt_at: datetime | None
    last_attempt_at: datetime | None
    response_status: int | None
    response_body: str
    error: str
    delivered_at: datetime | None
    created_at: datetime
    payload: dict[str, Any]


class SandboxReceipt(BaseModel):
    """Ответ песочницы ATS: событие принято и подпись проверена."""

    received: bool
    signature_valid: bool
    event_type: str | None
    event_id: uuid.UUID | None
    message: str
