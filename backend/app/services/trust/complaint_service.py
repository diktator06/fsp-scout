from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.crud import (
    audit_log_crud,
    company_crud,
    complaint_crud,
    invitation_crud,
    recruiter_crud,
    vacancy_crud,
)
from app.models.employer import Company
from app.models.notification import NotificationKind
from app.models.trust import ComplaintTarget
from app.models.user import User
from app.schemas.trust import ComplaintCreate, ComplaintRead
from app.services.candidate.profile_service import CandidateProfileService
from app.services.notifications import NotificationService

AUTO_RESTRICT_AUTHORS = 3
AUTO_RESTRICT_WINDOW = timedelta(days=30)


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class ComplaintService:
    """Жалобы кандидатов на компании и автоматическое ограничение.

    Если за 30 дней на компанию пожаловались три разных кандидата, она автоматически
    уходит на проверку: приглашения, вакансии и задачи приостанавливаются до решения
    модератора. Один кандидат в одиночку компанию не заблокирует.
    """

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._clock = clock
        self._profiles = CandidateProfileService(session)
        self._notifications = NotificationService(session, clock)

    async def file(self, user: User, payload: ComplaintCreate) -> ComplaintRead:
        """Принимает жалобу и при необходимости ограничивает компанию."""
        company = await self._company_for_target(user, payload)
        try:
            complaint = await complaint_crud.create(
                self._session,
                {
                    "company_id": company.id,
                    "author_user_id": user.id,
                    "target_type": payload.target_type,
                    "target_id": payload.target_id,
                    "reason": payload.reason,
                    "comment": payload.comment.strip(),
                },
            )
        except IntegrityError as error:
            await self._session.rollback()
            raise ConflictError(
                "Вы уже пожаловались на это — модератор рассмотрит жалобу"
            ) from error
        await audit_log_crud.record(
            self._session,
            actor_user_id=user.id,
            action="complaint_filed",
            entity_type="company",
            entity_id=company.id,
            meta={"complaint_id": str(complaint.id), "reason": payload.reason.value},
        )
        await self._auto_restrict(company)
        await self._session.commit()
        return ComplaintRead(
            id=complaint.id,
            target_type=complaint.target_type,
            target_id=complaint.target_id,
            reason=complaint.reason,
            comment=complaint.comment,
            status=complaint.status,
            resolution_note=complaint.resolution_note,
            created_at=complaint.created_at,
        )

    async def _company_for_target(self, user: User, payload: ComplaintCreate) -> Company:
        """Компания, на которую жалуются. Жаловаться можно только на то, что кандидат видел."""
        profile = await self._profiles.ensure_profile(user)
        company_id = None
        if payload.target_type is ComplaintTarget.INVITATION:
            invitation = await invitation_crud.get_for_candidate(
                self._session, payload.target_id, profile.id
            )
            company_id = invitation.company_id if invitation else None
        elif payload.target_type is ComplaintTarget.VACANCY:
            vacancy = await vacancy_crud.get(self._session, payload.target_id)
            company_id = vacancy.company_id if vacancy else None
        else:
            company_id = payload.target_id
        company = await company_crud.get(self._session, company_id) if company_id else None
        if company is None:
            raise NotFoundError("Объект жалобы не найден")
        return company

    async def _auto_restrict(self, company: Company) -> None:
        """Ограничивает компанию, если жалоб от разных кандидатов набралось достаточно."""
        if company.restricted_at is not None:
            return
        authors = await complaint_crud.distinct_open_authors(
            self._session, company.id, self._clock() - AUTO_RESTRICT_WINDOW
        )
        if authors < AUTO_RESTRICT_AUTHORS:
            return
        await company_crud.update(
            self._session,
            company,
            {
                "restricted_at": self._clock(),
                "restriction_reason": (
                    f"Автоматически: жалобы {authors} кандидатов за 30 дней, "
                    "ждёт проверки модератора"
                ),
            },
        )
        await audit_log_crud.record(
            self._session,
            actor_user_id=None,
            action="company_restricted",
            entity_type="company",
            entity_id=company.id,
            meta={"reason": "auto", "authors": authors},
        )
        for recruiter_user_id in await recruiter_crud.user_ids_for_company(
            self._session, company.id
        ):
            await self._notifications.notify(
                recruiter_user_id,
                NotificationKind.COMPANY_RESTRICTED,
                title="Компания на проверке",
                text="После жалоб кандидатов приглашения и вакансии приостановлены до решения "
                "модератора",
                link="/e/company",
            )
