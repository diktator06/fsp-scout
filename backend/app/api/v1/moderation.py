import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import MethodistUser, ModerationServiceDep
from app.api.errors import error_responses
from app.models.trust import ComplaintStatus
from app.schemas.trust import (
    ComplaintResolve,
    ModerationCompanyRead,
    ModerationComplaintRead,
    RestrictRequest,
    TrustLevelUpdate,
)

router = APIRouter(prefix="/moderation", tags=["moderation"])

_errors = error_responses(401, 403, 404, 409, 422)


@router.get(
    "/complaints",
    response_model=list[ModerationComplaintRead],
    responses=_errors,
    summary="Жалобы кандидатов",
)
async def complaints(
    user: MethodistUser,
    service: ModerationServiceDep,
    status: Annotated[ComplaintStatus | None, Query()] = None,
) -> list[ModerationComplaintRead]:
    """Очередь жалоб: открытые выше."""
    return await service.complaints(status)


@router.post(
    "/complaints/{complaint_id}/resolve",
    response_model=ModerationComplaintRead,
    responses=_errors,
    summary="Решение по жалобе",
)
async def resolve(
    complaint_id: uuid.UUID,
    payload: ComplaintResolve,
    user: MethodistUser,
    service: ModerationServiceDep,
) -> ModerationComplaintRead:
    """Подтверждённая жалоба попадает в репутацию компании, отклонённая — нет."""
    return await service.resolve(user, complaint_id, payload)


@router.get(
    "/companies",
    response_model=list[ModerationCompanyRead],
    responses=_errors,
    summary="Компании с сигналами",
)
async def companies(
    user: MethodistUser, service: ModerationServiceDep
) -> list[ModerationCompanyRead]:
    """Ограниченные, с жалобами и с подозрительными вилками — выше."""
    return await service.companies()


@router.post(
    "/companies/{company_id}/restrict",
    response_model=ModerationCompanyRead,
    responses=_errors,
    summary="Ограничить компанию",
)
async def restrict(
    company_id: uuid.UUID,
    payload: RestrictRequest,
    user: MethodistUser,
    service: ModerationServiceDep,
) -> ModerationCompanyRead:
    """Приглашения, вакансии и задачи компании приостанавливаются."""
    return await service.restrict(user, company_id, payload.reason)


@router.post(
    "/companies/{company_id}/lift",
    response_model=ModerationCompanyRead,
    responses=_errors,
    summary="Снять ограничение",
)
async def lift(
    company_id: uuid.UUID, user: MethodistUser, service: ModerationServiceDep
) -> ModerationCompanyRead:
    """Компания снова может приглашать и публиковать вакансии."""
    return await service.lift(user, company_id)


@router.put(
    "/companies/{company_id}/trust",
    response_model=ModerationCompanyRead,
    responses=_errors,
    summary="Уровень доверия компании",
)
async def set_trust(
    company_id: uuid.UUID,
    payload: TrustLevelUpdate,
    user: MethodistUser,
    service: ModerationServiceDep,
) -> ModerationCompanyRead:
    """От уровня доверия зависят дневная квота приглашений и лимит вакансий."""
    return await service.set_trust(user, company_id, payload.trust_level)
