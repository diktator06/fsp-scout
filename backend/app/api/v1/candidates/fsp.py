from fastapi import APIRouter, Depends, Response, status

from app.api.deps import CandidateUser, ClientContextDep, FspServiceDep
from app.api.errors import error_responses
from app.api.rate_limit import RateLimiter
from app.schemas.fsp import FspAuthorizationRead, FspCallback, FspLinkStart, FspProfileRead

router = APIRouter(prefix="/candidates/me/fsp", tags=["candidate: fsp"])

_errors = error_responses(401, 403, 404, 409, 422, 503)
sync_limiter = RateLimiter(limit=10, window_seconds=600)


@router.get("", response_model=FspProfileRead, responses=_errors, summary="Мой профиль ФСП")
async def fsp_profile(user: CandidateUser, service: FspServiceDep) -> FspProfileRead:
    """Состояние привязки, участия из реестра, балл ФСП и его вклад в индекс профиля.

    Все три случая штатные: не привязан, привязан без истории, привязан с участиями.
    """
    return await service.overview(user)


@router.post(
    "/link",
    response_model=FspAuthorizationRead,
    responses=_errors,
    summary="Начать привязку ФСП ID",
)
async def start_link(
    payload: FspLinkStart, user: CandidateUser, service: FspServiceDep
) -> FspAuthorizationRead:
    """Возвращает адрес страницы входа ФСП ID (код авторизации с PKCE).

    Согласие на получение данных из реестра ФСП обязательно и записывается в журнал
    согласий при завершении привязки.
    """
    return await service.start_link(user, payload)


@router.post(
    "/link/callback",
    response_model=FspProfileRead,
    responses=error_responses(400, 401, 403, 409, 422, 503),
    summary="Завершить привязку ФСП ID",
)
async def complete_link(
    payload: FspCallback, user: CandidateUser, service: FspServiceDep, client: ClientContextDep
) -> FspProfileRead:
    """Принимает code и state, которые ФСП ID вернул на адрес фронтенда, и загружает участия."""
    return await service.complete_link(user, payload, client)


@router.post(
    "/sync",
    response_model=FspProfileRead,
    responses=_errors,
    dependencies=[Depends(sync_limiter)],
    summary="Обновить участия из реестра ФСП",
)
async def sync(user: CandidateUser, service: FspServiceDep) -> FspProfileRead:
    """Перечитывает реестр. Если он недоступен, остаются прошлые данные, а в ответе — ошибка."""
    return await service.sync(user)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors,
    summary="Отвязать ФСП ID",
)
async def unlink(user: CandidateUser, service: FspServiceDep) -> Response:
    """Удаляет участия и привязку и отзывает согласие на получение данных ФСП."""
    await service.unlink(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
