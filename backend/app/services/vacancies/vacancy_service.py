import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
    VacancyLimitExceededError,
)
from app.crud import (
    application_crud,
    application_event_crud,
    candidate_profile_crud,
    company_crud,
    hiring_need_crud,
    skill_lookup_crud,
    specialization_crud,
    user_crud,
    vacancy_crud,
    vacancy_skill_crud,
)
from app.crud.candidate_search import PoolQuery
from app.models.employer import TrustLevel
from app.models.notification import NotificationKind
from app.models.user import User
from app.models.vacancy import Application, ApplicationStatus, Vacancy, VacancyStatus
from app.schemas.vacancy import (
    ApplicationDecision,
    EmployerApplicationRead,
    VacancyCreate,
    VacancyRead,
)
from app.services.contact_access import ContactAccessPolicy
from app.services.employer.company_service import CompanyService
from app.services.matching.candidate_pool import CandidatePoolService, members_by_id
from app.services.matching.cards import build_card
from app.services.matching.engine import MatchingEngine
from app.services.notifications import NotificationService
from app.services.trust.guard import ensure_company_active
from app.services.trust.market import MarketSalaryChecker
from app.services.vacancies.limits import published_vacancy_limit
from app.services.vacancies.state_machine import ApplicationActor, ensure_transition
from app.services.vacancies.views import application_events, vacancy_fields

REJECT_TEXTS = {
    "skills": "не хватает навыков из требований",
    "grade": "нужен другой уровень",
    "salary": "ожидания не совпали с вилкой",
    "position_filled": "позиция уже закрыта",
    "other": "другая причина",
}


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class VacancyService:
    """Вакансии работодателя: черновик, публикация с лимитом, закрытие и работа с откликами.

    Каждый публичный метод — одна транзакция. Статусы откликов меняются только по
    автомату, каждый переход пишется в журнал и виден обеим сторонам.
    """

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._clock = clock
        self._companies = CompanyService(session, clock)
        self._engine = MatchingEngine(session)
        self._pool = CandidatePoolService(session, clock)
        self._contacts = ContactAccessPolicy(session)
        self._notifications = NotificationService(session, clock)
        self._market = MarketSalaryChecker(self._pool)

    async def list_for_company(self, user: User) -> list[VacancyRead]:
        """Вакансии компании с воронкой откликов."""
        recruiter = await self._companies.require_recruiter(user)
        vacancies = await vacancy_crud.list_for_company(self._session, recruiter.company_id)
        return await self._views(list(vacancies))

    async def get(self, user: User, vacancy_id: uuid.UUID) -> VacancyRead:
        """Вакансия компании."""
        vacancy = await self._own(user, vacancy_id)
        return (await self._views([vacancy]))[0]

    async def create(self, user: User, payload: VacancyCreate, *, publish: bool) -> VacancyRead:
        """Создаёт вакансию черновиком или сразу публикует."""
        recruiter = await self._companies.require_recruiter(user)
        await self._validate(payload, recruiter.company_id)
        vacancy = await vacancy_crud.create(
            self._session,
            {
                **payload.model_dump(exclude={"skills"}),
                "company_id": recruiter.company_id,
                "author_user_id": user.id,
            },
        )
        await vacancy_skill_crud.replace_for_vacancy(
            self._session, vacancy.id, [(item.skill_id, item.importance) for item in payload.skills]
        )
        if publish:
            ensure_company_active(recruiter.company)
            await self._publish(vacancy, recruiter.company.trust_level)
        await self._session.commit()
        return (await self._views([vacancy]))[0]

    async def update(
        self, user: User, vacancy_id: uuid.UUID, payload: VacancyCreate
    ) -> VacancyRead:
        """Правит вакансию. Закрытую не правят: по ней уже идут отклики с прежними условиями."""
        vacancy = await self._own(user, vacancy_id, for_update=True)
        if vacancy.status is VacancyStatus.CLOSED:
            raise ConflictError("Закрытую вакансию нельзя изменить — создайте новую")
        await self._validate(payload, vacancy.company_id)
        for key, value in payload.model_dump(exclude={"skills"}).items():
            setattr(vacancy, key, value)
        await vacancy_skill_crud.replace_for_vacancy(
            self._session, vacancy.id, [(item.skill_id, item.importance) for item in payload.skills]
        )
        await self._session.commit()
        return (await self._views([vacancy]))[0]

    async def publish(self, user: User, vacancy_id: uuid.UUID) -> VacancyRead:
        """Публикует черновик или снова открывает закрытую вакансию."""
        recruiter = await self._companies.require_recruiter(user)
        vacancy = await self._own(user, vacancy_id, for_update=True)
        if vacancy.status is VacancyStatus.PUBLISHED:
            return (await self._views([vacancy]))[0]
        ensure_company_active(recruiter.company)
        await self._publish(vacancy, recruiter.company.trust_level)
        await self._session.commit()
        return (await self._views([vacancy]))[0]

    async def close(self, user: User, vacancy_id: uuid.UUID) -> VacancyRead:
        """Снимает вакансию с публикации: новые отклики не принимаются, старые остаются."""
        vacancy = await self._own(user, vacancy_id, for_update=True)
        if vacancy.status is not VacancyStatus.CLOSED:
            await vacancy_crud.update(
                self._session,
                vacancy,
                {"status": VacancyStatus.CLOSED, "closed_at": self._clock()},
            )
        await self._session.commit()
        return (await self._views([vacancy]))[0]

    async def applications(
        self, user: User, vacancy_id: uuid.UUID
    ) -> list[EmployerApplicationRead]:
        """Отклики на вакансию с карточками кандидатов и их контактами.

        Отклик сам открывает контакты, поэтому здесь они уже есть. Карточка строится так
        же, как в банке, — с индексом профиля и ФСП.
        """
        vacancy = await self._own(user, vacancy_id)
        applications = list(await application_crud.list_for_vacancy(self._session, vacancy.id))
        return await self._application_views(vacancy, applications)

    async def open_application(
        self, user: User, application_id: uuid.UUID
    ) -> EmployerApplicationRead:
        """Открывает отклик; первый просмотр отмечается — кандидат видит «просмотрено»."""
        recruiter = await self._companies.require_recruiter(user)
        application = await application_crud.get_for_company(
            self._session, application_id, recruiter.company_id, for_update=True
        )
        if application is None:
            raise NotFoundError("Отклик не найден")
        if application.status is ApplicationStatus.SUBMITTED:
            await self._move(
                application, ApplicationStatus.VIEWED, user, {"viewed_at": self._clock()}
            )
            await self._session.commit()
        vacancy = await vacancy_crud.get(self._session, application.vacancy_id)
        assert vacancy is not None
        return (await self._application_views(vacancy, [application]))[0]

    async def decide(
        self, user: User, application_id: uuid.UUID, payload: ApplicationDecision
    ) -> EmployerApplicationRead:
        """Решение по отклику: приглашение на собеседование или отказ с причиной."""
        recruiter = await self._companies.require_recruiter(user)
        application = await application_crud.get_for_company(
            self._session, application_id, recruiter.company_id, for_update=True
        )
        if application is None:
            raise NotFoundError("Отклик не найден")
        target = ApplicationStatus(payload.status)
        ensure_transition(application.status, target, ApplicationActor.EMPLOYER)
        now = self._clock()
        changes: dict[str, Any] = {
            "responded_at": now,
            "viewed_at": application.viewed_at or now,
            "reject_comment": payload.message,
        }
        if target is ApplicationStatus.REJECTED:
            changes["reject_reason"] = payload.reject_reason
        await self._move(application, target, user, changes)
        vacancy = await vacancy_crud.get(self._session, application.vacancy_id)
        assert vacancy is not None
        profile = await candidate_profile_crud.get(self._session, application.candidate_id)
        if profile is not None:
            await self._notify_candidate(profile.user_id, vacancy, application, payload)
        await self._session.commit()
        return (await self._application_views(vacancy, [application]))[0]

    async def _notify_candidate(
        self,
        candidate_user_id: uuid.UUID,
        vacancy: Vacancy,
        application: Application,
        payload: ApplicationDecision,
    ) -> None:
        """Уведомление кандидату о решении по отклику."""
        if application.status is ApplicationStatus.INTERVIEW:
            title = "Вас пригласили на собеседование"
            text = f"{vacancy.title}: компания ждёт вашего ответа. {payload.message}".strip()
        else:
            reason = REJECT_TEXTS.get(
                application.reject_reason.value if application.reject_reason else "other", ""
            )
            title = "Ответ по отклику"
            text = f"{vacancy.title}: отказ — {reason}. {payload.message}".strip()
        await self._notifications.notify(
            candidate_user_id,
            NotificationKind.APPLICATION_UPDATED,
            title=title,
            text=text,
            link="/c/applications",
        )

    async def _move(
        self,
        application: Application,
        target: ApplicationStatus,
        user: User,
        changes: dict[str, Any] | None = None,
    ) -> None:
        """Переводит отклик в новый статус и пишет переход в журнал."""
        await application_event_crud.create(
            self._session,
            {
                "application_id": application.id,
                "from_status": application.status,
                "to_status": target,
                "actor_user_id": user.id,
            },
        )
        await application_crud.update(
            self._session, application, {"status": target, **(changes or {})}
        )

    async def _publish(self, vacancy: Vacancy, trust_level: TrustLevel) -> None:
        """Публикует вакансию, если не исчерпан лимит одновременно открытых.

        Строка компании блокируется на время проверки: иначе две параллельные публикации
        разных вакансий увидели бы одно и то же число открытых и обе прошли бы лимит.
        """
        await company_crud.lock(self._session, vacancy.company_id)
        limit = published_vacancy_limit(trust_level)
        published = await vacancy_crud.count_by_status(
            self._session, vacancy.company_id, VacancyStatus.PUBLISHED
        )
        if published >= limit:
            raise VacancyLimitExceededError(details={"limit": limit})
        await vacancy_crud.update(
            self._session,
            vacancy,
            {"status": VacancyStatus.PUBLISHED, "published_at": self._clock(), "closed_at": None},
        )

    async def _own(self, user: User, vacancy_id: uuid.UUID, *, for_update: bool = False) -> Vacancy:
        """Вакансия своей компании или 404."""
        recruiter = await self._companies.require_recruiter(user)
        vacancy = await vacancy_crud.get_for_company(
            self._session, vacancy_id, recruiter.company_id, for_update=for_update
        )
        if vacancy is None:
            raise NotFoundError("Вакансия не найдена")
        return vacancy

    async def _validate(self, payload: VacancyCreate, company_id: uuid.UUID) -> None:
        """Справочные ссылки вакансии существуют, потребность принадлежит компании."""
        if await specialization_crud.get(self._session, payload.specialization_id) is None:
            raise DomainValidationError(
                "Специализация не найдена", details={"field": "specialization_id"}
            )
        catalog = await self._engine.catalog()
        if set(payload.grade_ids) - {grade.id for grade in catalog.grades}:
            raise DomainValidationError("Грейд не найден", details={"field": "grade_ids"})
        skill_ids = [item.skill_id for item in payload.skills]
        missing = sorted(
            set(skill_ids) - await skill_lookup_crud.existing_ids(self._session, skill_ids)
        )
        if missing:
            raise DomainValidationError(
                "Указаны несуществующие навыки", details={"skill_ids": missing}
            )
        if payload.need_id is not None and not await hiring_need_crud.get_for_company(
            self._session, payload.need_id, company_id
        ):
            raise NotFoundError("Потребность не найдена")

    async def _views(self, vacancies: list[Vacancy]) -> list[VacancyRead]:
        """Вакансии для ответа API вместе с числом откликов по статусам."""
        catalog = await self._engine.catalog()
        grades = {grade.id: grade for grade in catalog.grades}
        specializations = {
            item.id: item for item in await specialization_crud.list_all(self._session)
        }
        ids = [vacancy.id for vacancy in vacancies]
        skills = await vacancy_skill_crud.list_with_skills(self._session, ids)
        counts = await application_crud.status_counts(self._session, ids)
        result = []
        for vacancy in vacancies:
            by_status = counts.get(vacancy.id, {})
            result.append(
                VacancyRead(
                    **vacancy_fields(vacancy, skills.get(vacancy.id, []), specializations, grades),
                    status=vacancy.status,
                    need_id=vacancy.need_id,
                    closed_at=vacancy.closed_at,
                    created_at=vacancy.created_at,
                    updated_at=vacancy.updated_at,
                    applications_total=sum(by_status.values()),
                    applications_new=by_status.get(ApplicationStatus.SUBMITTED, 0),
                    applications_by_status=by_status,
                    market_check=await self._market.check(vacancy),
                )
            )
        return result

    async def _application_views(
        self, vacancy: Vacancy, applications: list[Application]
    ) -> list[EmployerApplicationRead]:
        """Отклики для работодателя: карточка, контакты и таймлайн."""
        candidate_ids = [item.candidate_id for item in applications]
        members = members_by_id(
            await self._pool.load(PoolQuery(candidate_ids=candidate_ids, published_only=False))
        )
        disclosures = await self._contacts.disclosures(vacancy.company_id, candidate_ids)
        events = await application_event_crud.list_for_applications(
            self._session, [item.id for item in applications]
        )
        emails = await user_crud.emails_by_ids(
            self._session, [member.row.profile.user_id for member in members.values()]
        )
        result = []
        for application in applications:
            member = members.get(application.candidate_id)
            profile = member.row.profile if member else None
            email = emails.get(profile.user_id) if profile else None
            contacts = (
                ContactAccessPolicy.contacts(
                    disclosures.get(application.candidate_id), profile, email, member.privacy
                )
                if member and profile and email
                else None
            )
            result.append(
                EmployerApplicationRead(
                    id=application.id,
                    status=application.status,
                    cover_letter=application.cover_letter,
                    reject_reason=application.reject_reason,
                    reject_comment=application.reject_comment,
                    created_at=application.created_at,
                    viewed_at=application.viewed_at,
                    responded_at=application.responded_at,
                    events=application_events(
                        events.get(application.id, []), profile.user_id if profile else None
                    ),
                    vacancy_id=vacancy.id,
                    match_score=application.match_score,
                    card=build_card(member) if member else None,
                    contacts=contacts,
                )
            )
        return result
