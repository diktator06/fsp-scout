from app.models.integration import WebhookEvent
from app.schemas.integration import WebhookEventInfo

EVENT_CATALOG: tuple[WebhookEventInfo, ...] = (
    WebhookEventInfo(
        type=WebhookEvent.INVITATION_ACCEPTED,
        title="Кандидат принял приглашение",
        description="Контакты открыты: карточку кандидата можно завести в ATS",
        contains_contacts=True,
    ),
    WebhookEventInfo(
        type=WebhookEvent.INVITATION_DECLINED,
        title="Кандидат отклонил приглашение",
        description="С причиной отказа, без контактов — для аналитики воронки",
        contains_contacts=False,
    ),
    WebhookEventInfo(
        type=WebhookEvent.APPLICATION_CREATED,
        title="Новый отклик на вакансию",
        description="Кандидат откликнулся сам и открыл контакты, балл соответствия — в событии",
        contains_contacts=True,
    ),
    WebhookEventInfo(
        type=WebhookEvent.APPLICATION_WITHDRAWN,
        title="Кандидат отозвал отклик",
        description="Карточку в ATS стоит закрыть",
        contains_contacts=False,
    ),
)

SUBSCRIBABLE_EVENTS = tuple(item.type for item in EVENT_CATALOG)
