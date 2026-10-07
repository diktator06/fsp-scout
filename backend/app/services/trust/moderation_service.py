import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.crud import (
    audit_log_crud,
    candidate_profile_crud,
    company_crud,
    complaint_crud,
    invitation_crud,
    vacancy_crud,
)
from app.crud.vacancy import VacancyQuery
from app.models.employer import Company, TrustLevel
from app.models.trust import Complaint, ComplaintStatus, ComplaintTarget
from app.models.user import User
from app.schemas.trust import (
    ComplaintResolve,
    ModerationCompanyBrief,
    ModerationCompanyRead,
    ModerationComplaintRead,
)
from app.services.matching.candidate_pool import CandidatePoolService
from app.services.trust.market import MarketSalaryChecker
from app.services.trust.reputation import company_reputations

MAX_COMPANIES = 500


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


def _brief(company: Company) -> ModerationCompanyBrief:
    """Компания в очереди модерации."""
    return ModerationCompanyBrief(
        id=company.id,
        name=company.name,
        inn=company.inn,
        trust_level=company.trust_level,
        restricted_at=company.restricted_at,
        restriction_reason=company.restriction_reason,
    )


class ModerationService:
    """Модерация работодателей: жалобы, ограничения и уровень доверия.

    Решения модератора пишутся в журнал аудита. Подтверждённая жалоба видна
    кандидатам в репутации компании; отклонённая — нет.
    """

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._clock = clock
        self._market = MarketSalaryChecker(CandidatePoolService(session, clock))

    async def complaints(self, status: ComplaintStatus | None) -> list[ModerationComplaintRead]:
        """Жалобы для модератора: открытые выше."""
        complaints = list(await complaint_crud.list_for_moderation(self._session, status))
        return [await self._complaint_read(item) for item in complaints]

    async def resolve(
        self, user: User, complaint_id: uuid.UUID, payload: ComplaintResolve
    ) -> ModerationComplaintRead:
        """Подтверждает или отклоняет жалобу."""
        complaint = await complaint_crud.get(self._session, complaint_id)
        if complaint is None:
            raise NotFoundError("Жалоба не найдена")
        if complaint.status is not ComplaintStatus.OPEN:
            raise ConflictError("Жалоба уже рассмотрена")
        complaint.status = ComplaintStatus(payload.status)
        complaint.resolution_note = payload.note.strip()
        complaint.resolved_by = user.id
        complaint.resolved_at = self._clock()
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action="complaint_resolved",
            entity_type="complaint",
            entity_id=complaint.id,
            meta={"status": complaint.status.value},
        )
        await self._session.commit()
        return await self._complaint_read(complaint)

    async def companies(self) -> list[ModerationCompanyRead]:
        """Компании с сигналами: ограниченные и с открытыми жалобами — выше."""
        companies = list(await company_crud.get_multi(self._session, limit=MAX_COMPANIES))
        reads = await self._company_reads(companies)
        reads.sort(
            key=lambda item: (
                item.restricted_at is None,
                -item.complaints_open,
                -len(item.suspicious_vacancies),
                item.name,
            )
        )
        return reads

    async def restrict(
        self, user: User, company_id: uuid.UUID, reason: str
    ) -> ModerationCompanyRead:
        """Ограничивает компанию вручную на время проверки."""
        company = await self._company(company_id)
        company.restricted_at = self._clock()
        company.restriction_reason = reason.strip()
        await self._audit(user, company, "company_restricted", {"reason": "manual"})
        await self._session.commit()
        return (await self._company_reads([company]))[0]

    async def lift(self, user: User, company_id: uuid.UUID) -> ModerationCompanyRead:
        """Снимает ограничение после проверки."""
        company = await self._company(company_id)
        company.restricted_at = None
        company.restriction_reason = ""
        await self._audit(user, company, "company_restriction_lifted", {})
        await self._session.commit()
        return (await self._company_reads([company]))[0]

    async def set_trust(
        self, user: User, company_id: uuid.UUID, level: TrustLevel
    ) -> ModerationCompanyRead:
        """Меняет уровень доверия: от него зависят квоты приглашений и вакансий."""
        company = await self._company(company_id)
        previous = company.trust_level
        company.trust_level = level
        await self._audit(
            user, company, "company_trust_changed", {"from": previous.value, "to": level.value}
        )
        await self._session.commit()
        return (await self._company_reads([company]))[0]

    async def _company(self, company_id: uuid.UUID) -> Company:
        """Компания или 404."""
        company = await company_crud.get(self._session, company_id)
        if company is None:
            raise NotFoundError("Компания не найдена")
        return company

    async def _audit(self, user: User, company: Company, action: str, meta: dict[str, str]) -> None:
        """Решение модератора — в журнал аудита."""
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action=action,
            entity_type="company",
            entity_id=company.id,
            meta=meta,
        )

    async def _company_reads(self, companies: list[Company]) -> list[ModerationCompanyRead]:
        """Компании с жалобами, репутацией и подозрительными вилками."""
        ids = [company.id for company in companies]
        complaints = await complaint_crud.counts_by_company(self._session, ids)
        reputations = await company_reputations(self._session, companies)
        result = []
        for company in companies:
            vacancies = await vacancy_crud.list_published(
                self._session, VacancyQuery(company_id=company.id)
            )
            suspicious = [
                vacancy.title
                for vacancy in vacancies
                if (await self._market.check(vacancy)).status == "suspicious"
            ]
            counts = complaints.get(company.id, {})
            result.append(
                ModerationCompanyRead(
                    **_brief(company).model_dump(),
                    complaints_open=counts.get(ComplaintStatus.OPEN, 0),
                    complaints_confirmed=counts.get(ComplaintStatus.CONFIRMED, 0),
                    reputation=reputations[company.id],
                    suspicious_vacancies=suspicious,
                    created_at=company.created_at,
                )
            )
        return result

    async def _complaint_read(self, complaint: Complaint) -> ModerationComplaintRead:
        """Жалоба с компанией, объектом и псевдонимом автора."""
        company = await self._company(complaint.company_id)
        title = company.name
        if complaint.target_type is ComplaintTarget.INVITATION:
            invitation = await invitation_crud.get(self._session, complaint.target_id)
            title = f"Приглашение «{invitation.title}»" if invitation else "Приглашение удалено"
        elif complaint.target_type is ComplaintTarget.VACANCY:
            vacancy = await vacancy_crud.get(self._session, complaint.target_id)
            title = f"Вакансия «{vacancy.title}»" if vacancy else "Вакансия удалена"
        profile = await candidate_profile_crud.get_by_user_id(
            self._session, complaint.author_user_id
        )
        return ModerationComplaintRead(
            id=complaint.id,
            target_type=complaint.target_type,
            target_id=complaint.target_id,
            reason=complaint.reason,
            comment=complaint.comment,
            status=complaint.status,
            resolution_note=complaint.resolution_note,
            created_at=complaint.created_at,
            company=_brief(company),
            target_title=title,
            author_alias=profile.public_alias if profile else None,
        )
