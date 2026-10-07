import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.dictionary import Skill
from app.models.employer import Company
from app.models.matching import SkillImportance
from app.models.vacancy import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    Vacancy,
    VacancySkill,
    VacancyStatus,
)


@dataclass(frozen=True, slots=True)
class VacancyQuery:
    """Фильтры списка опубликованных вакансий. Это параметры запроса, а не бизнес-правила."""

    specialization_id: int | None = None
    grade_id: int | None = None
    work_format: str | None = None
    salary_min: int | None = None
    text: str | None = None
    company_id: uuid.UUID | None = None


class VacancyCRUD(CRUDBase[Vacancy]):
    """Доступ к вакансиям."""

    async def get_for_company(
        self,
        session: AsyncSession,
        vacancy_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Vacancy | None:
        """Вакансия компании. Чужую не найти даже по точному id."""
        statement = select(Vacancy).where(
            Vacancy.id == vacancy_id, Vacancy.company_id == company_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def list_for_company(
        self, session: AsyncSession, company_id: uuid.UUID
    ) -> Sequence[Vacancy]:
        """Вакансии компании: сначала опубликованные, затем черновики и закрытые."""
        result = await session.scalars(
            select(Vacancy)
            .where(Vacancy.company_id == company_id)
            .order_by(
                case(
                    (Vacancy.status == VacancyStatus.PUBLISHED, 0),
                    (Vacancy.status == VacancyStatus.DRAFT, 1),
                    else_=2,
                ),
                Vacancy.updated_at.desc(),
            )
        )
        return result.all()

    async def count_by_status(
        self, session: AsyncSession, company_id: uuid.UUID, status: VacancyStatus
    ) -> int:
        """Сколько вакансий компании в статусе — для лимита публикаций."""
        total = await session.scalar(
            select(func.count())
            .select_from(Vacancy)
            .where(Vacancy.company_id == company_id, Vacancy.status == status)
        )
        return int(total or 0)

    async def get_published(self, session: AsyncSession, vacancy_id: uuid.UUID) -> Vacancy | None:
        """Опубликованная вакансия — только такие видят кандидаты."""
        return await session.scalar(
            select(Vacancy).where(
                Vacancy.id == vacancy_id, Vacancy.status == VacancyStatus.PUBLISHED
            )
        )

    async def list_published(self, session: AsyncSession, query: VacancyQuery) -> Sequence[Vacancy]:
        """Опубликованные вакансии по фильтрам, свежие выше."""
        statement = select(Vacancy).where(Vacancy.status == VacancyStatus.PUBLISHED)
        if query.specialization_id is not None:
            statement = statement.where(Vacancy.specialization_id == query.specialization_id)
        if query.grade_id is not None:
            statement = statement.where(Vacancy.grade_ids.contains([query.grade_id]))
        if query.work_format:
            statement = statement.where(Vacancy.work_formats.contains([query.work_format]))
        if query.salary_min is not None:
            statement = statement.where(Vacancy.salary_to >= query.salary_min)
        if query.company_id is not None:
            statement = statement.where(Vacancy.company_id == query.company_id)
        if query.text:
            pattern = f"%{query.text.strip()}%"
            statement = statement.where(
                or_(Vacancy.title.ilike(pattern), Vacancy.description.ilike(pattern))
            )
        result = await session.scalars(statement.order_by(Vacancy.published_at.desc()))
        return result.all()


class VacancySkillCRUD(CRUDBase[VacancySkill]):
    """Доступ к навыкам вакансий."""

    async def list_with_skills(
        self, session: AsyncSession, vacancy_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[tuple[VacancySkill, Skill]]]:
        """Навыки пачки вакансий: обязательные раньше желательных."""
        ids = list(set(vacancy_ids))
        if not ids:
            return {}
        result = await session.execute(
            select(VacancySkill, Skill)
            .join(Skill, Skill.id == VacancySkill.skill_id)
            .where(VacancySkill.vacancy_id.in_(ids))
            .order_by(VacancySkill.importance, Skill.name)
        )
        grouped: dict[uuid.UUID, list[tuple[VacancySkill, Skill]]] = {}
        for item, skill in result.all():
            grouped.setdefault(item.vacancy_id, []).append((item, skill))
        return grouped

    async def replace_for_vacancy(
        self,
        session: AsyncSession,
        vacancy_id: uuid.UUID,
        skills: Sequence[tuple[int, SkillImportance]],
    ) -> None:
        """Заменяет навыки вакансии целиком."""
        await session.execute(delete(VacancySkill).where(VacancySkill.vacancy_id == vacancy_id))
        session.add_all(
            VacancySkill(vacancy_id=vacancy_id, skill_id=skill_id, importance=importance)
            for skill_id, importance in skills
        )
        await session.flush()


class ApplicationCRUD(CRUDBase[Application]):
    """Доступ к откликам."""

    async def get_for_candidate(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        candidate_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Application | None:
        """Отклик кандидата. Чужой не найти даже по точному id."""
        statement = select(Application).where(
            Application.id == application_id, Application.candidate_id == candidate_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def get_for_company(
        self,
        session: AsyncSession,
        application_id: uuid.UUID,
        company_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> Application | None:
        """Отклик на вакансию компании."""
        statement = select(Application).where(
            Application.id == application_id, Application.company_id == company_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await session.scalar(statement)

    async def get_by_pair(
        self, session: AsyncSession, vacancy_id: uuid.UUID, candidate_id: uuid.UUID
    ) -> Application | None:
        """Отклик кандидата на конкретную вакансию."""
        return await session.scalar(
            select(Application).where(
                Application.vacancy_id == vacancy_id, Application.candidate_id == candidate_id
            )
        )

    async def list_for_candidate(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> Sequence[Application]:
        """Отклики кандидата, свежие выше."""
        result = await session.scalars(
            select(Application)
            .where(Application.candidate_id == candidate_id)
            .order_by(Application.created_at.desc())
        )
        return result.all()

    async def list_for_vacancy(
        self, session: AsyncSession, vacancy_id: uuid.UUID
    ) -> Sequence[Application]:
        """Отклики на вакансию: новые и непросмотренные выше."""
        result = await session.scalars(
            select(Application)
            .where(Application.vacancy_id == vacancy_id)
            .order_by(Application.status, Application.created_at.desc())
        )
        return result.all()

    async def status_counts(
        self, session: AsyncSession, vacancy_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, dict[ApplicationStatus, int]]:
        """Сколько откликов в каждом статусе по каждой вакансии."""
        ids = list(set(vacancy_ids))
        if not ids:
            return {}
        result = await session.execute(
            select(Application.vacancy_id, Application.status, func.count())
            .where(Application.vacancy_id.in_(ids))
            .group_by(Application.vacancy_id, Application.status)
        )
        counts: dict[uuid.UUID, dict[ApplicationStatus, int]] = {}
        for vacancy_id, status, total in result.all():
            counts.setdefault(vacancy_id, {})[status] = int(total)
        return counts

    async def applied_vacancy_ids(
        self, session: AsyncSession, candidate_id: uuid.UUID
    ) -> dict[uuid.UUID, Application]:
        """Отклики кандидата по вакансиям — для меток в списке."""
        result = await session.scalars(
            select(Application).where(Application.candidate_id == candidate_id)
        )
        return {item.vacancy_id: item for item in result.all()}


class ApplicationEventCRUD(CRUDBase[ApplicationEvent]):
    """Доступ к журналу откликов."""

    async def list_for_applications(
        self, session: AsyncSession, application_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[ApplicationEvent]]:
        """События пачки откликов по порядку."""
        ids = list(set(application_ids))
        if not ids:
            return {}
        result = await session.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id.in_(ids))
            .order_by(ApplicationEvent.created_at)
        )
        grouped: dict[uuid.UUID, list[ApplicationEvent]] = {}
        for event in result.all():
            grouped.setdefault(event.application_id, []).append(event)
        return grouped


class CompanyLookupCRUD:
    """Компании пачкой — для списков вакансий у кандидата."""

    async def with_industry(
        self, session: AsyncSession, company_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, Company]:
        """Компании с отраслью по идентификаторам."""
        ids = list(set(company_ids))
        if not ids:
            return {}
        result = await session.scalars(
            select(Company).options(selectinload(Company.industry)).where(Company.id.in_(ids))
        )
        return {item.id: item for item in result.all()}


vacancy_crud = VacancyCRUD(Vacancy)
vacancy_skill_crud = VacancySkillCRUD(VacancySkill)
application_crud = ApplicationCRUD(Application)
application_event_crud = ApplicationEventCRUD(ApplicationEvent)
company_lookup_crud = CompanyLookupCRUD()
