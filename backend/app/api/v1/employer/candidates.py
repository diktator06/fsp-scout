import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import BankServiceDep, EmployerUser, PaginationDep
from app.api.errors import error_responses
from app.models.candidate import WorkFormat
from app.schemas.matching import BankFilters, BankPage, BankSort, CandidateCardRead

router = APIRouter(prefix="/employer/candidates", tags=["employer: bank"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.get("", response_model=BankPage, responses=_errors, summary="Банк кандидатов")
async def search_candidates(
    user: EmployerUser,
    service: BankServiceDep,
    pagination: PaginationDep,
    specialization_id: Annotated[int | None, Query()] = None,
    grade_id: Annotated[int | None, Query()] = None,
    category_id: Annotated[int | None, Query()] = None,
    skill_ids: Annotated[list[int] | None, Query(description="Все перечисленные навыки")] = None,
    verified_skills_only: Annotated[bool, Query(description="Навыки подтверждены тестом")] = False,
    confirmed_only: Annotated[bool, Query(description="Только с подтверждённым грейдом")] = False,
    work_format: Annotated[WorkFormat | None, Query()] = None,
    city: Annotated[str | None, Query(max_length=120)] = None,
    has_fsp: Annotated[bool, Query(description="Есть подтверждённые участия в ФСП")] = False,
    sort: Annotated[BankSort, Query()] = BankSort.SCORE,
) -> BankPage:
    """Обезличенные карточки кандидатов, давших согласие на публикацию.

    По умолчанию подтверждённые тестом идут раньше заявленных, внутри — по индексу
    подтверждённого профиля.
    """
    filters = BankFilters(
        specialization_id=specialization_id,
        grade_id=grade_id,
        category_id=category_id,
        skill_ids=skill_ids or [],
        verified_skills_only=verified_skills_only,
        confirmed_only=confirmed_only,
        work_format=work_format,
        city=city,
        has_fsp=has_fsp,
        sort=sort,
    )
    return await service.search(user, filters, limit=pagination.limit, offset=pagination.offset)


@router.get(
    "/{candidate_id}",
    response_model=CandidateCardRead,
    responses=_errors,
    summary="Карточка кандидата",
)
async def candidate_card(
    candidate_id: uuid.UUID,
    user: EmployerUser,
    service: BankServiceDep,
    need_id: Annotated[uuid.UUID | None, Query(description="Потребность для балла")] = None,
) -> CandidateCardRead:
    """Обезличенная карточка; контакты — только если кандидат раскрыл их компании."""
    return await service.card(user, candidate_id, need_id)
