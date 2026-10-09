import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import EmployerUser, IntegrationServiceDep, SandboxReceiverDep
from app.api.errors import error_responses
from app.api.rate_limit import RateLimiter
from app.schemas.integration import (
    SandboxReceipt,
    WebhookDeliveryRead,
    WebhookEndpointCreate,
    WebhookEndpointRead,
    WebhookEndpointSecretRead,
    WebhookEndpointUpdate,
    WebhookEventInfo,
)
from app.services.integrations.export import ExportFormat

router = APIRouter(prefix="/employer/integrations", tags=["integrations"])
sandbox_router = APIRouter(prefix="/integrations", tags=["integrations"])
sandbox_limiter = RateLimiter(limit=120, window_seconds=60)
export_limiter = RateLimiter(limit=30, window_seconds=3600)

_errors = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/events",
    response_model=list[WebhookEventInfo],
    responses=error_responses(401, 403),
    summary="Каталог событий",
)
async def events(user: EmployerUser, service: IntegrationServiceDep) -> list[WebhookEventInfo]:
    """События, на которые ATS может подписаться, и есть ли в них контакты кандидата."""
    return service.events()


@router.get(
    "/webhooks",
    response_model=list[WebhookEndpointRead],
    responses=_errors,
    summary="Получатели вебхуков",
)
async def endpoints(
    user: EmployerUser, service: IntegrationServiceDep
) -> list[WebhookEndpointRead]:
    """Подключённые адреса ATS компании. Секрет показан подсказкой."""
    return await service.endpoints(user)


@router.post(
    "/webhooks",
    status_code=status.HTTP_201_CREATED,
    response_model=WebhookEndpointSecretRead,
    responses=_errors,
    summary="Подключить ATS",
)
async def create_endpoint(
    payload: WebhookEndpointCreate, user: EmployerUser, service: IntegrationServiceDep
) -> WebhookEndpointSecretRead:
    """Адрес проверяется на доступность из интернета (защита от SSRF).

    Полный секрет подписи возвращается только в этом ответе — сохраните его в ATS.
    """
    return await service.create_endpoint(user, payload)


@router.post(
    "/sandbox",
    status_code=status.HTTP_201_CREATED,
    response_model=WebhookEndpointSecretRead,
    responses=_errors,
    summary="Подключить песочницу ATS",
)
async def connect_sandbox(
    user: EmployerUser, service: IntegrationServiceDep
) -> WebhookEndpointSecretRead:
    """Встроенный получатель на все события: проверить интеграцию без своей ATS."""
    return await service.connect_sandbox(user)


@router.patch(
    "/webhooks/{endpoint_id}",
    response_model=WebhookEndpointRead,
    responses=_errors,
    summary="Изменить подписку",
)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    payload: WebhookEndpointUpdate,
    user: EmployerUser,
    service: IntegrationServiceDep,
) -> WebhookEndpointRead:
    """События, описание, включение и отключение получателя."""
    return await service.update_endpoint(user, endpoint_id, payload)


@router.post(
    "/webhooks/{endpoint_id}/secret",
    response_model=WebhookEndpointSecretRead,
    responses=_errors,
    summary="Сменить секрет подписи",
)
async def rotate_secret(
    endpoint_id: uuid.UUID, user: EmployerUser, service: IntegrationServiceDep
) -> WebhookEndpointSecretRead:
    """Старый секрет перестаёт действовать сразу."""
    return await service.rotate_secret(user, endpoint_id)


@router.post(
    "/webhooks/{endpoint_id}/test",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WebhookDeliveryRead,
    responses=_errors,
    summary="Проверить связь",
)
async def test_endpoint(
    endpoint_id: uuid.UUID, user: EmployerUser, service: IntegrationServiceDep
) -> WebhookDeliveryRead:
    """Ставит в очередь событие `ping`; итог появится в журнале доставок."""
    return await service.test_endpoint(user, endpoint_id)


@router.delete(
    "/webhooks/{endpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors,
    summary="Отключить ATS",
)
async def delete_endpoint(
    endpoint_id: uuid.UUID, user: EmployerUser, service: IntegrationServiceDep
) -> Response:
    """Удаляет получателя вместе с журналом его доставок."""
    await service.delete_endpoint(user, endpoint_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/deliveries",
    response_model=list[WebhookDeliveryRead],
    responses=_errors,
    summary="Журнал доставок",
)
async def deliveries(
    user: EmployerUser, service: IntegrationServiceDep
) -> list[WebhookDeliveryRead]:
    """Последние 50 доставок: статус, попытки, ответ получателя и тело события."""
    return await service.deliveries(user)


@router.post(
    "/deliveries/{delivery_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WebhookDeliveryRead,
    responses=_errors,
    summary="Повторить доставку",
)
async def redeliver(
    delivery_id: uuid.UUID, user: EmployerUser, service: IntegrationServiceDep
) -> WebhookDeliveryRead:
    """Новая попытка с тем же `event_id`: получатель распознает повтор."""
    return await service.redeliver(user, delivery_id)


@router.get(
    "/export",
    responses={
        200: {
            "content": {"text/csv": {}, "application/json": {}},
            "description": "Файл с кандидатами, открывшими компании контакты",
        },
        **error_responses(401, 403, 409, 429),
    },
    dependencies=[Depends(export_limiter)],
    summary="Выгрузка кандидатов для ATS",
)
async def export(
    user: EmployerUser,
    service: IntegrationServiceDep,
    fmt: Annotated[ExportFormat, Query(alias="format")] = "csv",
) -> Response:
    """Все, кто принял приглашение или откликнулся. Каждая выгрузка пишется в аудит."""
    file = await service.export(user, fmt)
    return Response(
        content=file.content,
        media_type=file.media_type,
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )


@sandbox_router.post(
    "/sandbox/receive",
    response_model=SandboxReceipt,
    responses=error_responses(401, 404, 429),
    dependencies=[Depends(sandbox_limiter)],
    summary="Песочница ATS: приём вебхука",
)
async def sandbox_receive(request: Request, receiver: SandboxReceiverDep) -> SandboxReceipt:
    """Принимает событие и проверяет подпись `X-Scout-Signature`, как настоящая ATS."""
    return await receiver.receive(request.headers, await request.body())
