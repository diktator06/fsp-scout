import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, NotificationServiceDep
from app.api.errors import error_responses
from app.schemas.notification import NotificationListRead

router = APIRouter(prefix="/notifications", tags=["notifications"])

_errors = error_responses(401, 404)


@router.get("", response_model=NotificationListRead, responses=_errors, summary="Мои уведомления")
async def list_notifications(
    user: CurrentUser, service: NotificationServiceDep
) -> NotificationListRead:
    """Последние уведомления и число непрочитанных."""
    return await service.list(user)


@router.post(
    "/read-all",
    response_model=NotificationListRead,
    responses=_errors,
    summary="Отметить все прочитанными",
)
async def read_all(user: CurrentUser, service: NotificationServiceDep) -> NotificationListRead:
    """Отмечает все уведомления прочитанными."""
    return await service.mark_read(user)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationListRead,
    responses=_errors,
    summary="Отметить уведомление прочитанным",
)
async def read_one(
    notification_id: uuid.UUID, user: CurrentUser, service: NotificationServiceDep
) -> NotificationListRead:
    """Отмечает одно уведомление прочитанным."""
    return await service.mark_read(user, notification_id)
