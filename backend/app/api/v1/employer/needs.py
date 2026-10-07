import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import EmployerUser, NeedServiceDep, ShortlistServiceDep
from app.api.errors import error_responses
from app.models.matching import NeedStatus
from app.schemas.matching import (
    CategorySliceRead,
    MarkUpdate,
    NeedCreate,
    NeedDraft,
    NeedParseRequest,
    NeedRead,
    ShortlistFilters,
    ShortlistRead,
)

router = APIRouter(prefix="/employer/needs", tags=["employer: needs"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.post(
    "/parse",
    response_model=NeedDraft,
    responses=_errors,
    summary="Разобрать текст потребности",
)
async def parse_need(
    payload: NeedParseRequest, user: EmployerUser, service: NeedServiceDep
) -> NeedDraft:
    """Свободный текст → специализация, грейды, навыки must/nice, формат, город, вилка.

    Разбор работает на правилах и справочнике навыков, без внешних моделей. Каждое
    поле сопровождается фрагментом текста, по которому оно найдено. Ничего не сохраняет.
    """
    return await service.parse(user, payload.text)


@router.get("", response_model=list[NeedRead], responses=_errors, summary="Потребности компании")
async def list_needs(user: EmployerUser, service: NeedServiceDep) -> list[NeedRead]:
    """Все потребности компании, от новых к старым."""
    return await service.list_needs(user)


@router.post(
    "",
    response_model=NeedRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors,
    summary="Создать потребность",
)
async def create_need(payload: NeedCreate, user: EmployerUser, service: NeedServiceDep) -> NeedRead:
    """Сохраняет потребность. Вилка обязательна и не шире чем вдвое."""
    return await service.create(user, payload)


@router.get("/{need_id}", response_model=NeedRead, responses=_errors, summary="Потребность")
async def read_need(need_id: uuid.UUID, user: EmployerUser, service: NeedServiceDep) -> NeedRead:
    """Потребность компании. Чужая — 404."""
    return await service.get(user, need_id)


@router.put(
    "/{need_id}", response_model=NeedRead, responses=_errors, summary="Изменить потребность"
)
async def update_need(
    need_id: uuid.UUID, payload: NeedCreate, user: EmployerUser, service: NeedServiceDep
) -> NeedRead:
    """Изменяет потребность. Уже построенные версии подборки не меняются."""
    return await service.update(user, need_id, payload)


@router.post(
    "/{need_id}/close", response_model=NeedRead, responses=_errors, summary="Закрыть потребность"
)
async def close_need(need_id: uuid.UUID, user: EmployerUser, service: NeedServiceDep) -> NeedRead:
    """Переводит потребность в архив."""
    return await service.set_status(user, need_id, NeedStatus.CLOSED)


@router.post(
    "/{need_id}/reopen",
    response_model=NeedRead,
    responses=_errors,
    summary="Вернуть потребность в работу",
)
async def reopen_need(need_id: uuid.UUID, user: EmployerUser, service: NeedServiceDep) -> NeedRead:
    """Возвращает потребность из архива."""
    return await service.set_status(user, need_id, NeedStatus.ACTIVE)


@router.get(
    "/{need_id}/categories",
    response_model=list[CategorySliceRead],
    responses=_errors,
    summary="Рекомендованные категории с рыночным срезом",
)
async def need_categories(
    need_id: uuid.UUID, user: EmployerUser, service: NeedServiceDep
) -> list[CategorySliceRead]:
    """Целевая и соседние категории: сколько кандидатов, сколько сильных, медиана ожиданий."""
    return await service.categories(user, need_id)


@router.post(
    "/{need_id}/shortlists",
    response_model=ShortlistRead,
    status_code=status.HTTP_201_CREATED,
    responses=_errors,
    summary="Уточнить подборку (новая версия)",
)
async def build_shortlist(
    need_id: uuid.UUID,
    filters: ShortlistFilters,
    user: EmployerUser,
    service: ShortlistServiceDep,
) -> ShortlistRead:
    """Строит новую версию подборки с фильтрами. Закреплённые кандидаты переносятся."""
    return await service.build(user, need_id, filters)


@router.get(
    "/{need_id}/shortlist",
    response_model=ShortlistRead,
    responses=_errors,
    summary="Подборка (последняя или указанная версия)",
)
async def read_shortlist(
    need_id: uuid.UUID,
    user: EmployerUser,
    service: ShortlistServiceDep,
    version: Annotated[int | None, Query(ge=1, description="Номер версии")] = None,
) -> ShortlistRead:
    """Ранжированная подборка с баллом, разложением и «Почему в подборке»."""
    return await service.get(user, need_id, version)


@router.put(
    "/{need_id}/marks/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors,
    summary="Закрепить или скрыть кандидата",
)
async def set_mark(
    need_id: uuid.UUID,
    candidate_id: uuid.UUID,
    payload: MarkUpdate,
    user: EmployerUser,
    service: ShortlistServiceDep,
) -> Response:
    """Отметка действует на все следующие версии подборки этой потребности."""
    await service.set_mark(user, need_id, candidate_id, payload)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{need_id}/marks/{candidate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_errors,
    summary="Снять отметку",
)
async def remove_mark(
    need_id: uuid.UUID, candidate_id: uuid.UUID, user: EmployerUser, service: ShortlistServiceDep
) -> Response:
    """Снимает отметку «закреплён» или «скрыт»."""
    await service.remove_mark(user, need_id, candidate_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
