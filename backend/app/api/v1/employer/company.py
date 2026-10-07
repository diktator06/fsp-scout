from fastapi import APIRouter

from app.api.deps import CompanyServiceDep, EmployerUser
from app.api.errors import error_responses
from app.schemas.employer import CompanyUpdate, EmployerDashboardRead, EmployerProfileRead

router = APIRouter(prefix="/employer", tags=["employer"])

_errors = error_responses(401, 403, 409, 422)


@router.get(
    "/company", response_model=EmployerProfileRead, responses=_errors, summary="Моя компания"
)
async def read_company(user: EmployerUser, service: CompanyServiceDep) -> EmployerProfileRead:
    """Профиль компании, рекрутер и квота приглашений. До заполнения — пустые поля."""
    return await service.get_profile(user)


@router.put(
    "/company",
    response_model=EmployerProfileRead,
    responses=_errors,
    summary="Сохранить профиль компании",
)
async def save_company(
    payload: CompanyUpdate, user: EmployerUser, service: CompanyServiceDep
) -> EmployerProfileRead:
    """Создаёт компанию при первом сохранении, дальше обновляет её."""
    return await service.save_profile(user, payload)


@router.get(
    "/dashboard",
    response_model=EmployerDashboardRead,
    responses=_errors,
    summary="Сводка кабинета работодателя",
)
async def dashboard(user: EmployerUser, service: CompanyServiceDep) -> EmployerDashboardRead:
    """Активные потребности, воронка приглашений и остаток дневной квоты."""
    return await service.dashboard(user)
