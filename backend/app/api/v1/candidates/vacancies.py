import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CandidateUser, PaginationDep, VacancyBoardServiceDep
from app.api.errors import error_responses
from app.crud.vacancy import VacancyQuery
from app.models.candidate import WorkFormat
from app.schemas.vacancy import (
    ApplicationCreate,
    CandidateApplicationRead,
    VacancyBoardPage,
    VacancyPublicRead,
)

router = APIRouter(tags=["candidate: vacancies"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/vacancies", response_model=VacancyBoardPage, responses=_errors, summary="Открытые вакансии"
)
async def vacancy_board(
    user: CandidateUser,
    service: VacancyBoardServiceDep,
    pagination: PaginationDep,
    specialization_id: Annotated[int | None, Query()] = None,
    grade_id: Annotated[int | None, Query()] = None,
    work_format: Annotated[WorkFormat | None, Query()] = None,
    salary_min: Annotated[
        int | None, Query(gt=0, description="Верхняя граница вилки не ниже")
    ] = None,
    text: Annotated[
        str | None, Query(max_length=100, description="Поиск в названии и описании")
    ] = None,
) -> VacancyBoardPage:
    """Опубликованные вакансии с баллом соответствия кандидату и отметкой об отклике.

    Если кандидат прошёл опрос, список упорядочен по соответствию — тем же правилам,
    по которым работодатель видит подборку.
    """
    query = VacancyQuery(
        specialization_id=specialization_id,
        grade_id=grade_id,
        work_format=work_format.value if work_format else None,
        salary_min=salary_min,
        text=text,
    )
    return await service.board(user, query, limit=pagination.limit, offset=pagination.offset)


@router.get(
    "/vacancies/{vacancy_id}",
    response_model=VacancyPublicRead,
    responses=_errors,
    summary="Вакансия",
)
async def read_vacancy(
    vacancy_id: uuid.UUID, user: CandidateUser, service: VacancyBoardServiceDep
) -> VacancyPublicRead:
    """Вакансия с компанией, вилкой и объяснением соответствия."""
    return await service.get(user, vacancy_id)


@router.post(
    "/vacancies/{vacancy_id}/applications",
    status_code=status.HTTP_201_CREATED,
    response_model=CandidateApplicationRead,
    responses=_errors,
    summary="Откликнуться",
)
async def apply(
    vacancy_id: uuid.UUID,
    payload: ApplicationCreate,
    user: CandidateUser,
    service: VacancyBoardServiceDep,
) -> CandidateApplicationRead:
    """Отклик открывает компании контакты кандидата — с его явного согласия."""
    return await service.apply(user, vacancy_id, payload)


@router.get(
    "/candidates/me/applications",
    response_model=list[CandidateApplicationRead],
    responses=_errors,
    summary="Мои отклики",
)
async def my_applications(
    user: CandidateUser, service: VacancyBoardServiceDep
) -> list[CandidateApplicationRead]:
    """Отклики со статусами и таймлайном."""
    return await service.my_applications(user)


@router.post(
    "/candidates/me/applications/{application_id}/withdraw",
    response_model=CandidateApplicationRead,
    responses=_errors,
    summary="Отозвать отклик",
)
async def withdraw(
    application_id: uuid.UUID, user: CandidateUser, service: VacancyBoardServiceDep
) -> CandidateApplicationRead:
    """Можно, пока компания не ответила."""
    return await service.withdraw(user, application_id)
