import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, ConsentRequiredError, NotFoundError
from app.crud import (
    application_crud,
    application_event_crud,
    company_lookup_crud,
    recruiter_crud,
    specialization_crud,
    vacancy_crud,
    vacancy_skill_crud,
)
from app.crud.candidate_search import PoolQuery
from app.crud.vacancy import VacancyQuery
from app.models.dictionary import Skill
from app.models.invitation import DisclosureReason
from app.models.notification import NotificationKind
from app.models.user import User
from app.models.vacancy import (
    Application,
    ApplicationStatus,
    Vacancy,
    VacancySkill,
    VacancyStatus,
)
from app.schemas.matching import ExplanationItemRead, MatchRead
from app.schemas.vacancy import (
    ApplicationBrief,
    ApplicationCreate,
    CandidateApplicationRead,
    VacancyBoardPage,
    VacancyBriefRead,
    VacancyPublicRead,
)
from app.services.candidate.profile_service import CandidateProfileService
from app.services.contact_access import ContactAccessPolicy
from app.services.employer.company_views import company_brief, employer_contacts
from app.services.integrations.publisher import WebhookPublisher
from app.services.matching.candidate_pool import CandidatePoolService, PoolMember
from app.services.matching.engine import MatchingEngine
from app.services.matching.views import match_read, match_snapshot
from app.services.notifications import NotificationService
from app.services.trust.reputation import company_reputations
from app.services.vacancies.state_machine import ApplicationActor, ensure_transition
from app.services.vacancies.views import application_events, for_candidate, vacancy_fields

OTHER_SPECIALIZATION_FACTOR = 0.6


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class VacancyBoardService:
    """Вакансии глазами кандидата: лента с баллом соответствия, отклик и мои отклики.

    Это дополнительный канал к основной механике: кандидат, которого ещё не пригласили,
    может проявить инициативу сам. Балл считается теми же правилами, что и подборка
    работодателя, поэтому обе стороны видят одну и ту же картину соответствия.
    """

    def __init__(
        self, session: AsyncSession, settings: Settings, clock: Callable[[], datetime] = _now
    ) -> None:
        """Получает сессию БД, настройки и источник времени."""
        self._session = session
        self._clock = clock
        self._webhooks = WebhookPublisher(session, settings, clock)
        self._profiles = CandidateProfileService(session)
        self._pool = CandidatePoolService(session, clock)
        self._engine = MatchingEngine(session)
        self._contacts = ContactAccessPolicy(session)
        self._notifications = NotificationService(session, clock)

    async def board(
        self, user: User, query: VacancyQuery, *, limit: int, offset: int
    ) -> VacancyBoardPage:
        """Опубликованные вакансии; если кандидат прошёл опрос — по убыванию соответствия."""
        profile = await self._profiles.ensure_profile(user)
        await self._session.commit()
        member = await self._member(profile.id)
        vacancies = list(await vacancy_crud.list_published(self._session, query))
        reads = await self._public_views(vacancies, member, profile.id)
        if member is not None:
            reads.sort(key=lambda item: item.match.score if item.match else 0.0, reverse=True)
        return VacancyBoardPage(
            items=reads[offset : offset + limit], total=len(reads), can_apply=member is not None
        )

    async def get(self, user: User, vacancy_id: uuid.UUID) -> VacancyPublicRead:
        """Вакансия с баллом и объяснением. Закрытую видит только тот, кто на неё откликнулся."""
        profile = await self._profiles.ensure_profile(user)
        vacancy = await vacancy_crud.get(self._session, vacancy_id)
        applied = await application_crud.get_by_pair(self._session, vacancy_id, profile.id)
        if vacancy is None or (vacancy.status is not VacancyStatus.PUBLISHED and applied is None):
            raise NotFoundError("Вакансия не найдена или снята с публикации")
        member = await self._member(profile.id)
        return (await self._public_views([vacancy], member, profile.id))[0]

    async def apply(
        self, user: User, vacancy_id: uuid.UUID, payload: ApplicationCreate
    ) -> CandidateApplicationRead:
        """Отклик на вакансию.

        Отклик — собственная инициатива кандидата, поэтому он в той же транзакции
        открывает компании контакты (ТЗ §2.2) — с явным согласием. Без опроса
        откликаться рано: работодателю нечего показать, кроме письма.
        """
        if not payload.share_contacts:
            raise ConsentRequiredError(
                "Отклик открывает компании ваши контакты — подтвердите согласие"
            )
        profile = await self._profiles.ensure_profile(user)
        member = await self._member(profile.id)
        if member is None:
            raise ConflictError(
                "Сначала пройдите опрос: работодатель увидит вашу категорию и подтверждённые навыки"
            )
        vacancy = await vacancy_crud.get_published(self._session, vacancy_id)
        if vacancy is None:
            raise NotFoundError("Вакансия не найдена или снята с публикации")
        if await application_crud.get_by_pair(self._session, vacancy.id, profile.id):
            raise ConflictError("Вы уже откликнулись на эту вакансию")
        skills = await vacancy_skill_crud.list_with_skills(self._session, [vacancy.id])
        match = await self._match(member, vacancy, skills.get(vacancy.id, []))
        try:
            application = await application_crud.create(
                self._session,
                {
                    "vacancy_id": vacancy.id,
                    "company_id": vacancy.company_id,
                    "candidate_id": profile.id,
                    "cover_letter": payload.cover_letter,
                    "match_score": match.score,
                },
            )
        except IntegrityError as error:
            await self._session.rollback()
            raise ConflictError("Вы уже откликнулись на эту вакансию") from error
        await application_event_crud.create(
            self._session,
            {
                "application_id": application.id,
                "from_status": None,
                "to_status": ApplicationStatus.SUBMITTED,
                "actor_user_id": user.id,
            },
        )
        await self._contacts.disclose(
            company_id=vacancy.company_id,
            candidate_id=profile.id,
            reason=DisclosureReason.APPLICATION,
            source_id=application.id,
            actor_user_id=user.id,
        )
        for recruiter_user_id in await recruiter_crud.user_ids_for_company(
            self._session, vacancy.company_id
        ):
            await self._notifications.notify(
                recruiter_user_id,
                NotificationKind.APPLICATION_RECEIVED,
                title="Новый отклик",
                text=f"Кандидат {profile.public_alias} откликнулся на «{vacancy.title}»",
                link=f"/e/vacancies/{vacancy.id}",
            )
        await self._webhooks.application_created(application, vacancy)
        await self._session.commit()
        return (await self._application_views([application], profile.user_id))[0]

    async def withdraw(self, user: User, application_id: uuid.UUID) -> CandidateApplicationRead:
        """Отзывает отклик, пока компания не ответила. Раскрытые контакты остаются у компании."""
        profile = await self._profiles.ensure_profile(user)
        application = await application_crud.get_for_candidate(
            self._session, application_id, profile.id, for_update=True
        )
        if application is None:
            raise NotFoundError("Отклик не найден")
        ensure_transition(
            application.status, ApplicationStatus.WITHDRAWN, ApplicationActor.CANDIDATE
        )
        await application_event_crud.create(
            self._session,
            {
                "application_id": application.id,
                "from_status": application.status,
                "to_status": ApplicationStatus.WITHDRAWN,
                "actor_user_id": user.id,
            },
        )
        application.status = ApplicationStatus.WITHDRAWN
        application.responded_at = self._clock()
        vacancy = await vacancy_crud.get(self._session, application.vacancy_id)
        assert vacancy is not None
        await self._webhooks.application_withdrawn(application, vacancy, profile.public_alias)
        await self._session.commit()
        return (await self._application_views([application], profile.user_id))[0]

    async def my_applications(self, user: User) -> list[CandidateApplicationRead]:
        """Отклики кандидата со статусами. Чужие отклики не видны никогда."""
        profile = await self._profiles.ensure_profile(user)
        await self._session.commit()
        applications = list(await application_crud.list_for_candidate(self._session, profile.id))
        return await self._application_views(applications, profile.user_id)

    async def _member(self, candidate_id: uuid.UUID) -> PoolMember | None:
        """Кандидат как участник подбора; None, пока нет опроса."""
        members = await self._pool.load(
            PoolQuery(candidate_ids=[candidate_id], published_only=False)
        )
        return members[0] if members else None

    async def _match(
        self,
        member: PoolMember,
        vacancy: Vacancy,
        skills: Sequence[tuple[VacancySkill, Skill]],
    ) -> MatchRead:
        """Балл соответствия кандидата вакансии с объяснением от его лица.

        Подборка работодателя отсекает чужие специализации жёстким фильтром, а в ленте
        кандидат видит всё. Поэтому вакансия другой специализации здесь не исчезает,
        а получает понижающий множитель и честное пояснение.
        """
        catalog = await self._engine.catalog()
        context = await self._engine.build_context(
            specialization_id=vacancy.specialization_id,
            grade_ids=vacancy.grade_ids,
            skills=[(item.skill_id, item.importance) for item, _ in skills],
            salary_from=vacancy.salary_from,
            salary_to=vacancy.salary_to,
            salary_gross=vacancy.salary_gross,
            work_formats=vacancy.work_formats,
            city=vacancy.city,
            texts=(vacancy.title, vacancy.description),
        )
        scored = (await self._engine.score(context, [member]))[0]
        read = match_read(match_snapshot(scored.result, scored.explanation), catalog.names)
        explanation = [
            ExplanationItemRead(kind=item.kind, text=for_candidate(item.text))
            for item in read.explanation
        ]
        if member.facts.specialization_id != vacancy.specialization_id:
            read.score = round(read.score * OTHER_SPECIALIZATION_FACTOR, 1)
            explanation.insert(
                0,
                ExplanationItemRead(
                    kind="minus",
                    text=f"Вакансия для другой специализации — у вас {member.category.title}",
                ),
            )
        read.explanation = explanation
        return read

    async def _public_views(
        self, vacancies: list[Vacancy], member: PoolMember | None, candidate_id: uuid.UUID
    ) -> list[VacancyPublicRead]:
        """Вакансии для кандидата: компания, вилка, балл и отметка об отклике."""
        catalog = await self._engine.catalog()
        grades = {grade.id: grade for grade in catalog.grades}
        specializations = {
            item.id: item for item in await specialization_crud.list_all(self._session)
        }
        ids = [vacancy.id for vacancy in vacancies]
        skills = await vacancy_skill_crud.list_with_skills(self._session, ids)
        companies = await company_lookup_crud.with_industry(
            self._session, [vacancy.company_id for vacancy in vacancies]
        )
        applied = await application_crud.applied_vacancy_ids(self._session, candidate_id)
        reputations = await company_reputations(self._session, list(companies.values()))
        result = []
        for vacancy in vacancies:
            vacancy_skills = skills.get(vacancy.id, [])
            application = applied.get(vacancy.id)
            result.append(
                VacancyPublicRead(
                    **vacancy_fields(vacancy, vacancy_skills, specializations, grades),
                    company=company_brief(
                        companies[vacancy.company_id], reputations.get(vacancy.company_id)
                    ),
                    match=await self._match(member, vacancy, vacancy_skills) if member else None,
                    application=ApplicationBrief(
                        id=application.id,
                        status=application.status,
                        created_at=application.created_at,
                    )
                    if application
                    else None,
                )
            )
        return result

    async def _application_views(
        self, applications: list[Application], candidate_user_id: uuid.UUID
    ) -> list[CandidateApplicationRead]:
        """Отклики кандидата: вакансия, компания, таймлайн и контакты после приглашения."""
        vacancies = {}
        for application in applications:
            vacancy = await vacancy_crud.get(self._session, application.vacancy_id)
            if vacancy is not None:
                vacancies[vacancy.id] = vacancy
        companies = await company_lookup_crud.with_industry(
            self._session, [vacancy.company_id for vacancy in vacancies.values()]
        )
        events = await application_event_crud.list_for_applications(
            self._session, [item.id for item in applications]
        )
        reputations = await company_reputations(self._session, list(companies.values()))
        result = []
        for application in applications:
            vacancy = vacancies[application.vacancy_id]
            company = companies[vacancy.company_id]
            recruiter = (
                await recruiter_crud.get_by_user_id(self._session, vacancy.author_user_id)
                if vacancy.author_user_id
                else None
            )
            result.append(
                CandidateApplicationRead(
                    id=application.id,
                    status=application.status,
                    cover_letter=application.cover_letter,
                    reject_reason=application.reject_reason,
                    reject_comment=application.reject_comment,
                    created_at=application.created_at,
                    viewed_at=application.viewed_at,
                    responded_at=application.responded_at,
                    events=application_events(events.get(application.id, []), candidate_user_id),
                    vacancy=VacancyBriefRead(
                        id=vacancy.id,
                        title=vacancy.title,
                        status=vacancy.status,
                        salary_from=vacancy.salary_from,
                        salary_to=vacancy.salary_to,
                        salary_gross=vacancy.salary_gross,
                        company=company_brief(company, reputations.get(company.id)),
                    ),
                    employer_contacts=employer_contacts(company, recruiter)
                    if application.status is ApplicationStatus.INTERVIEW
                    else None,
                )
            )
        return result
