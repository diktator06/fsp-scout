import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import (
    AssessmentItem,
    AssessmentSession,
    Competency,
    ItemFamily,
    SessionStatus,
    SurveyResponse,
)
from app.models.candidate import (
    CandidateProfile,
    CandidateSkill,
    PrivacySettings,
    SearchStatus,
    WorkExperience,
)
from app.models.consent import Consent, ConsentType
from app.models.dictionary import Category, Skill, SkillRelation, SpecializationSkill
from app.models.user import User


@dataclass(frozen=True, slots=True)
class PoolQuery:
    """Параметры выборки кандидатов из банка. Это фильтры запроса, а не бизнес-правила."""

    specialization_ids: Sequence[int] = ()
    grade_ids: Sequence[int] = ()
    category_ids: Sequence[int] = ()
    candidate_ids: Sequence[uuid.UUID] = ()
    skill_ids: Sequence[int] = ()
    verified_skills_only: bool = False
    confirmed_only: bool = False
    work_formats: Sequence[str] = ()
    city: str | None = None
    published_only: bool = True


@dataclass(frozen=True, slots=True)
class PoolRow:
    """Кандидат из выборки: профиль, заявленная по опросу категория и служебные признаки."""

    profile: CandidateProfile
    email_verified: bool
    published: bool
    claimed_specialization_id: int | None
    claimed_grade_id: int | None


@dataclass(frozen=True, slots=True)
class CompetencyOutcome:
    """Итог по одной компетенции теста."""

    code: str
    name: str
    answered: int
    correct: float


@dataclass
class PoolExtras:
    """Связанные данные пачки кандидатов, загруженные одним запросом на вид данных."""

    skills: dict[uuid.UUID, list[tuple[CandidateSkill, Skill]]] = field(default_factory=dict)
    privacy: dict[uuid.UUID, PrivacySettings] = field(default_factory=dict)
    experiences: dict[uuid.UUID, list[WorkExperience]] = field(default_factory=dict)
    sessions: dict[uuid.UUID, AssessmentSession] = field(default_factory=dict)


def _latest_surveys() -> Select[uuid.UUID, int, int]:
    """Последний опрос каждого кандидата: из него берётся заявленная категория."""
    return (
        select(
            SurveyResponse.candidate_id,
            SurveyResponse.specialization_id,
            SurveyResponse.claimed_grade_id,
        )
        .ext(distinct_on(SurveyResponse.candidate_id))
        .order_by(SurveyResponse.candidate_id, SurveyResponse.created_at.desc())
    )


class CandidatePoolCRUD:
    """Выборки для банка кандидатов и подбора: фильтры, пачки связанных данных, статистика."""

    async def search(self, session: AsyncSession, query: PoolQuery) -> list[PoolRow]:
        """Кандидаты по фильтрам вместе с подтверждённой или заявленной категорией.

        Эффективная специализация и грейд — из категории, присвоенной тестом, а если
        её нет — из последнего опроса. Кандидаты без опроса в банк не попадают:
        работодателю нечего о них сказать.
        """
        surveys = _latest_surveys().subquery()
        published = (
            exists()
            .where(
                Consent.user_id == CandidateProfile.user_id,
                Consent.consent_type == ConsentType.BANK_PUBLICATION,
                Consent.revoked_at.is_(None),
            )
            .correlate(CandidateProfile)
        )
        specialization = func.coalesce(Category.specialization_id, surveys.c.specialization_id)
        grade = func.coalesce(Category.grade_id, surveys.c.claimed_grade_id)
        statement = (
            select(
                CandidateProfile,
                User.is_email_verified,
                published.label("published"),
                surveys.c.specialization_id,
                surveys.c.claimed_grade_id,
            )
            .join(User, User.id == CandidateProfile.user_id)
            .outerjoin(Category, Category.id == CandidateProfile.current_category_id)
            .outerjoin(surveys, surveys.c.candidate_id == CandidateProfile.id)
            .options(
                selectinload(CandidateProfile.current_category).selectinload(
                    Category.specialization
                ),
                selectinload(CandidateProfile.current_category).selectinload(Category.grade),
            )
            .where(User.is_active.is_(True), specialization.is_not(None))
        )
        if query.published_only:
            statement = statement.where(
                published, CandidateProfile.search_status != SearchStatus.NOT_LOOKING
            )
        if query.specialization_ids:
            statement = statement.where(specialization.in_(list(query.specialization_ids)))
        if query.grade_ids:
            statement = statement.where(grade.in_(list(query.grade_ids)))
        if query.category_ids:
            statement = statement.where(
                or_(
                    CandidateProfile.current_category_id.in_(list(query.category_ids)),
                    and_(
                        CandidateProfile.current_category_id.is_(None),
                        exists()
                        .where(
                            Category.id.in_(list(query.category_ids)),
                            Category.specialization_id == surveys.c.specialization_id,
                            Category.grade_id == surveys.c.claimed_grade_id,
                        )
                        .correlate(surveys),
                    ),
                )
            )
        if query.candidate_ids:
            statement = statement.where(CandidateProfile.id.in_(list(query.candidate_ids)))
        if query.confirmed_only:
            statement = statement.where(CandidateProfile.current_category_id.is_not(None))
        for skill_id in query.skill_ids:
            condition = [
                CandidateSkill.candidate_id == CandidateProfile.id,
                CandidateSkill.skill_id == skill_id,
            ]
            if query.verified_skills_only:
                condition.append(CandidateSkill.is_verified.is_(True))
            statement = statement.where(exists().where(*condition).correlate(CandidateProfile))
        if query.work_formats:
            statement = statement.where(
                CandidateProfile.work_formats.overlap(list(query.work_formats))
            )
        if query.city:
            statement = statement.where(
                func.lower(CandidateProfile.city) == query.city.strip().lower(),
                exists()
                .where(
                    PrivacySettings.candidate_id == CandidateProfile.id,
                    PrivacySettings.show_city.is_(True),
                )
                .correlate(CandidateProfile),
            )
        result = await session.execute(statement)
        return [
            PoolRow(
                profile=profile,
                email_verified=bool(email_verified),
                published=bool(is_published),
                claimed_specialization_id=claimed_specialization,
                claimed_grade_id=claimed_grade,
            )
            for profile, email_verified, is_published, claimed_specialization, claimed_grade in (
                result.all()
            )
        ]

    async def load_extras(
        self, session: AsyncSession, candidate_ids: Iterable[uuid.UUID]
    ) -> PoolExtras:
        """Навыки, приватность, опыт и последний результативный тест для пачки кандидатов."""
        ids = list(set(candidate_ids))
        extras = PoolExtras()
        if not ids:
            return extras
        skills = await session.execute(
            select(CandidateSkill, Skill)
            .join(Skill, Skill.id == CandidateSkill.skill_id)
            .where(CandidateSkill.candidate_id.in_(ids))
            .order_by(Skill.name)
        )
        for candidate_skill, skill in skills.all():
            extras.skills.setdefault(candidate_skill.candidate_id, []).append(
                (candidate_skill, skill)
            )
        privacy = await session.scalars(
            select(PrivacySettings).where(PrivacySettings.candidate_id.in_(ids))
        )
        extras.privacy = {item.candidate_id: item for item in privacy.all()}
        experiences = await session.scalars(
            select(WorkExperience)
            .where(WorkExperience.candidate_id.in_(ids))
            .order_by(WorkExperience.started_on.desc())
        )
        for experience in experiences.all():
            extras.experiences.setdefault(experience.candidate_id, []).append(experience)
        sessions = await session.scalars(
            select(AssessmentSession)
            .where(
                AssessmentSession.candidate_id.in_(ids),
                AssessmentSession.status == SessionStatus.COMPLETED,
                AssessmentSession.resulting_category_id.is_not(None),
            )
            .order_by(AssessmentSession.candidate_id, AssessmentSession.finished_at.desc())
            .ext(distinct_on(AssessmentSession.candidate_id))
        )
        extras.sessions = {item.candidate_id: item for item in sessions.all()}
        return extras

    async def category_thetas(
        self, session: AsyncSession, category_ids: Iterable[int]
    ) -> dict[int, list[float]]:
        """Оценки θ подтверждённых кандидатов по категориям: база для перцентиля в индексе.

        Берётся последний тест, который присвоил кандидату его текущую категорию.
        """
        ids = list(set(category_ids))
        if not ids:
            return {}
        latest = (
            select(AssessmentSession.resulting_category_id, AssessmentSession.theta)
            .join(
                CandidateProfile,
                and_(
                    CandidateProfile.id == AssessmentSession.candidate_id,
                    CandidateProfile.current_category_id == AssessmentSession.resulting_category_id,
                ),
            )
            .where(
                AssessmentSession.resulting_category_id.in_(ids),
                AssessmentSession.status == SessionStatus.COMPLETED,
            )
            .order_by(AssessmentSession.candidate_id, AssessmentSession.finished_at.desc())
            .ext(distinct_on(AssessmentSession.candidate_id))
        )
        result = await session.execute(latest)
        grouped: dict[int, list[float]] = {}
        for category_id, theta in result.all():
            if category_id is not None:
                grouped.setdefault(category_id, []).append(float(theta))
        return grouped

    async def competency_outcomes(
        self, session: AsyncSession, session_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, list[CompetencyOutcome]]:
        """Сколько заданий и сколько верных по каждой компетенции теста (без пилотных)."""
        ids = list(set(session_ids))
        if not ids:
            return {}
        result = await session.execute(
            select(
                AssessmentItem.session_id,
                Competency.code,
                Competency.name,
                func.count(),
                func.sum(AssessmentItem.score),
            )
            .join(ItemFamily, ItemFamily.id == AssessmentItem.family_id)
            .join(Competency, Competency.id == ItemFamily.competency_id)
            .where(
                AssessmentItem.session_id.in_(ids),
                AssessmentItem.score.is_not(None),
                AssessmentItem.is_pilot.is_(False),
            )
            .group_by(AssessmentItem.session_id, Competency.code, Competency.name)
            .order_by(AssessmentItem.session_id, func.count().desc(), Competency.name)
        )
        grouped: dict[uuid.UUID, list[CompetencyOutcome]] = {}
        for session_id, code, name, answered, correct in result.all():
            grouped.setdefault(session_id, []).append(
                CompetencyOutcome(
                    code=code, name=name, answered=int(answered), correct=float(correct or 0)
                )
            )
        return grouped

    async def specialization_skill_weights(
        self, session: AsyncSession, specialization_ids: Iterable[int]
    ) -> dict[tuple[int, int], float]:
        """Насколько навык типичен для специализации: ключ (специализация, навык)."""
        ids = list(set(specialization_ids))
        if not ids:
            return {}
        result = await session.execute(
            select(
                SpecializationSkill.specialization_id,
                SpecializationSkill.skill_id,
                SpecializationSkill.typical_weight,
            ).where(SpecializationSkill.specialization_id.in_(ids))
        )
        return {
            (int(spec_id), int(skill_id)): float(weight)
            for spec_id, skill_id, weight in result.all()
        }

    async def skill_relations(self, session: AsyncSession) -> dict[int, dict[int, float]]:
        """Родственные навыки: для каждого навыка — похожие и степень похожести."""
        result = await session.execute(
            select(SkillRelation.skill_id, SkillRelation.related_skill_id, SkillRelation.similarity)
        )
        relations: dict[int, dict[int, float]] = {}
        for skill_id, related_id, similarity in result.all():
            relations.setdefault(int(skill_id), {})[int(related_id)] = float(similarity)
        return relations


candidate_pool_crud = CandidatePoolCRUD()
