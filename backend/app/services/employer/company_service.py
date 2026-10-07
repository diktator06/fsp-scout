from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CompanyRequiredError, DomainValidationError, PermissionDeniedError
from app.crud import company_crud, hiring_need_crud, industry_crud, invitation_crud, recruiter_crud
from app.models.employer import Recruiter
from app.models.invitation import InvitationStatus
from app.models.matching import NeedStatus
from app.models.user import User, UserRole
from app.schemas.employer import (
    CompanyRead,
    CompanyUpdate,
    EmployerDashboardRead,
    EmployerProfileRead,
    InvitationQuotaRead,
    RecruiterRead,
)
from app.services.invitations.quotas import daily_limit


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class CompanyService:
    """Профиль компании и права рекрутера действовать от её имени."""

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._clock = clock

    async def require_recruiter(self, user: User) -> Recruiter:
        """Рекрутер с компанией. Без заполненного профиля компании подбор недоступен."""
        if user.role is not UserRole.EMPLOYER:
            raise PermissionDeniedError("Раздел доступен только работодателям")
        recruiter = await recruiter_crud.get_by_user_id(self._session, user.id)
        if recruiter is None:
            raise CompanyRequiredError()
        return recruiter

    async def quota(self, recruiter: Recruiter) -> InvitationQuotaRead:
        """Квота приглашений за последние сутки (скользящее окно, а не календарный день)."""
        limit = daily_limit(recruiter.company.trust_level)
        used = await invitation_crud.count_created_since(
            self._session, recruiter.company_id, self._clock() - timedelta(days=1)
        )
        return InvitationQuotaRead(
            daily_limit=limit, used_today=used, remaining=max(0, limit - used)
        )

    async def get_profile(self, user: User) -> EmployerProfileRead:
        """Профиль работодателя; до заполнения компании поля пустые."""
        recruiter = await recruiter_crud.get_by_user_id(self._session, user.id)
        if recruiter is None:
            return EmployerProfileRead(company=None, recruiter=None, quota=None)
        return EmployerProfileRead(
            company=CompanyRead.model_validate(recruiter.company),
            recruiter=RecruiterRead.model_validate(recruiter),
            quota=await self.quota(recruiter),
        )

    async def save_profile(self, user: User, payload: CompanyUpdate) -> EmployerProfileRead:
        """Создаёт компанию при первом сохранении или обновляет существующую.

        Пользователь, создавший компанию, становится её рекрутером. Уровень доверия
        сам работодатель не меняет: его выставляет платформа по итогам проверок.
        """
        if user.role is not UserRole.EMPLOYER:
            raise PermissionDeniedError("Профиль компании доступен только работодателям")
        if payload.industry_id is not None and not await industry_crud.get(
            self._session, payload.industry_id
        ):
            raise DomainValidationError("Отрасль не найдена", details={"field": "industry_id"})
        company_fields = payload.model_dump(exclude={"recruiter_full_name", "recruiter_position"})
        recruiter_fields = {
            "full_name": payload.recruiter_full_name,
            "position": payload.recruiter_position,
        }
        recruiter = await recruiter_crud.get_by_user_id(self._session, user.id)
        if recruiter is None:
            company = await company_crud.create(self._session, company_fields)
            await recruiter_crud.create(
                self._session, {"user_id": user.id, "company_id": company.id, **recruiter_fields}
            )
        else:
            await company_crud.update(self._session, recruiter.company, company_fields)
            await recruiter_crud.update(self._session, recruiter, recruiter_fields)
        await self._session.commit()
        return await self.get_profile(user)

    async def dashboard(self, user: User) -> EmployerDashboardRead:
        """Сводка для главной кабинета: активные потребности и воронка приглашений."""
        recruiter = await self.require_recruiter(user)
        needs = await hiring_need_crud.list_for_company(
            self._session, recruiter.company_id, NeedStatus.ACTIVE
        )
        counts = await invitation_crud.status_counts(self._session, recruiter.company_id)
        return EmployerDashboardRead(
            active_needs=len(needs),
            invitations={status: counts.get(status, 0) for status in InvitationStatus},
            accepted_contacts=counts.get(InvitationStatus.ACCEPTED, 0),
            quota=await self.quota(recruiter),
        )
