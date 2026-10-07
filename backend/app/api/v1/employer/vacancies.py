import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import EmployerUser, VacancyServiceDep
from app.api.errors import error_responses
from app.schemas.vacancy import (
    ApplicationDecision,
    EmployerApplicationRead,
    VacancyCreate,
    VacancyRead,
)

router = APIRouter(prefix="/employer", tags=["employer: vacancies"])

_errors = error_responses(401, 403, 404, 409, 422, 429)


@router.get(
    "/vacancies", response_model=list[VacancyRead], responses=_errors, summary="Вакансии компании"
)
async def list_vacancies(user: EmployerUser, service: VacancyServiceDep) -> list[VacancyRead]:
    """Вакансии компании с числом откликов по статусам."""
    return await service.list_for_company(user)


@router.post(
    "/vacancies",
    status_code=status.HTTP_201_CREATED,
    response_model=VacancyRead,
    responses=_errors,
    summary="Создать вакансию",
)
async def create_vacancy(
    payload: VacancyCreate,
    user: EmployerUser,
    service: VacancyServiceDep,
    publish: Annotated[bool, Query(description="Сразу опубликовать")] = True,
) -> VacancyRead:
    """Создаёт вакансию. Вилка «от–до» обязательна; публикация ограничена уровнем доверия."""
    return await service.create(user, payload, publish=publish)


@router.get(
    "/vacancies/{vacancy_id}", response_model=VacancyRead, responses=_errors, summary="Вакансия"
)
async def read_vacancy(
    vacancy_id: uuid.UUID, user: EmployerUser, service: VacancyServiceDep
) -> VacancyRead:
    """Вакансия своей компании; чужая — 404."""
    return await service.get(user, vacancy_id)


@router.put(
    "/vacancies/{vacancy_id}",
    response_model=VacancyRead,
    responses=_errors,
    summary="Изменить вакансию",
)
async def update_vacancy(
    vacancy_id: uuid.UUID, payload: VacancyCreate, user: EmployerUser, service: VacancyServiceDep
) -> VacancyRead:
    """Правит черновик или опубликованную вакансию."""
    return await service.update(user, vacancy_id, payload)


@router.post(
    "/vacancies/{vacancy_id}/publish",
    response_model=VacancyRead,
    responses=_errors,
    summary="Опубликовать вакансию",
)
async def publish_vacancy(
    vacancy_id: uuid.UUID, user: EmployerUser, service: VacancyServiceDep
) -> VacancyRead:
    """Публикует черновик или снова открывает закрытую вакансию."""
    return await service.publish(user, vacancy_id)


@router.post(
    "/vacancies/{vacancy_id}/close",
    response_model=VacancyRead,
    responses=_errors,
    summary="Снять с публикации",
)
async def close_vacancy(
    vacancy_id: uuid.UUID, user: EmployerUser, service: VacancyServiceDep
) -> VacancyRead:
    """Новые отклики не принимаются, прежние остаются в работе."""
    return await service.close(user, vacancy_id)


@router.get(
    "/vacancies/{vacancy_id}/applications",
    response_model=list[EmployerApplicationRead],
    responses=_errors,
    summary="Отклики на вакансию",
)
async def vacancy_applications(
    vacancy_id: uuid.UUID, user: EmployerUser, service: VacancyServiceDep
) -> list[EmployerApplicationRead]:
    """Отклики с карточками, баллом соответствия и контактами кандидатов."""
    return await service.applications(user, vacancy_id)


@router.get(
    "/applications/{application_id}",
    response_model=EmployerApplicationRead,
    responses=_errors,
    summary="Отклик (отмечается просмотренным)",
)
async def read_application(
    application_id: uuid.UUID, user: EmployerUser, service: VacancyServiceDep
) -> EmployerApplicationRead:
    """Первое открытие переводит отклик в «просмотрено» — это видит кандидат."""
    return await service.open_application(user, application_id)


@router.post(
    "/applications/{application_id}/decision",
    response_model=EmployerApplicationRead,
    responses=_errors,
    summary="Ответ на отклик",
)
async def decide_application(
    application_id: uuid.UUID,
    payload: ApplicationDecision,
    user: EmployerUser,
    service: VacancyServiceDep,
) -> EmployerApplicationRead:
    """Приглашение на собеседование или отказ с причиной; кандидат получает уведомление."""
    return await service.decide(user, application_id, payload)
