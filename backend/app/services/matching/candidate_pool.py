import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    candidate_pool_crud,
    category_crud,
    fsp_achievement_crud,
    fsp_link_crud,
    microtask_assignment_crud,
)
from app.crud.candidate_search import PoolQuery, PoolRow
from app.models.assessment import AssessmentMode, AssessmentSession
from app.models.candidate import CandidateSkill, PrivacySettings, WorkExperience
from app.models.dictionary import Category, Skill
from app.models.fsp import FspResultStatus
from app.models.microtask import MicroTask, MicroTaskAssignment
from app.services.candidate.profile_service import profile_completeness
from app.services.fsp.achievements_scoring import describe_result, summarize
from app.services.fsp.standing import NOT_LINKED, FspStanding, fsp_standing
from app.services.matching.facts import AssessmentFact, CandidateFacts, SkillFact
from app.services.matching.verified_score import VerifiedScore, compute_verified_score
from app.services.microtasks.freshness import GradedResult, freshness


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


@dataclass(slots=True)
class PoolMember:
    """Кандидат пула: факты для подбора, индекс профиля и исходные данные для карточки."""

    row: PoolRow
    facts: CandidateFacts
    score: VerifiedScore
    category: Category
    skills: list[tuple[CandidateSkill, Skill]] = field(default_factory=list)
    privacy: PrivacySettings | None = None
    experiences: list[WorkExperience] = field(default_factory=list)
    session: AssessmentSession | None = None
    fsp: FspStanding = NOT_LINKED
    micro_tasks: list[tuple[MicroTaskAssignment, MicroTask]] = field(default_factory=list)

    @property
    def candidate_id(self) -> uuid.UUID:
        """Идентификатор профиля кандидата."""
        return self.row.profile.id


class CandidatePoolService:
    """Собирает кандидатов из банка в форму, понятную подбору: факты, индекс, категорию.

    Одна выборка обслуживает и банк, и подборку, и карточку, поэтому кандидат везде
    выглядит одинаково и с одним и тем же индексом.
    """

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени (от него зависит давность теста)."""
        self._session = session
        self._clock = clock
        self._categories: dict[tuple[int, int], Category] | None = None

    async def categories(self) -> dict[tuple[int, int], Category]:
        """Все категории со специализацией и грейдом по паре (специализация, грейд)."""
        if self._categories is None:
            items = await category_crud.list_filtered(self._session)
            self._categories = {(item.specialization_id, item.grade_id): item for item in items}
        return self._categories

    async def band(self, category: Category) -> tuple[float, float | None]:
        """Полоса категории на шкале θ: её порог и порог следующего грейда."""
        categories = await self.categories()
        higher = sorted(
            (
                item
                for item in categories.values()
                if item.specialization_id == category.specialization_id
                and item.grade.rank > category.grade.rank
            ),
            key=lambda item: item.grade.rank,
        )
        return category.theta_cut, higher[0].theta_cut if higher else None

    async def load(self, query: PoolQuery) -> list[PoolMember]:
        """Кандидаты по фильтрам с фактами и индексом подтверждённого профиля."""
        rows = await candidate_pool_crud.search(self._session, query)
        if not rows:
            return []
        categories = await self.categories()
        ids = [row.profile.id for row in rows]
        extras = await candidate_pool_crud.load_extras(self._session, ids)
        fsp_links = await fsp_link_crud.for_candidates(self._session, ids)
        fsp_achievements = await fsp_achievement_crud.for_candidates(self._session, fsp_links)
        micro_tasks = await microtask_assignment_crud.graded_for_candidates(self._session, ids)
        confirmed_categories = {
            row.profile.current_category_id
            for row in rows
            if row.profile.current_category_id is not None
        }
        peers = await candidate_pool_crud.category_thetas(self._session, confirmed_categories)
        now = self._clock()
        members = []
        for row in rows:
            category = self._effective_category(row, categories)
            if category is None:
                continue
            member = PoolMember(
                row=row,
                facts=CandidateFacts(
                    candidate_id=row.profile.id,
                    alias=row.profile.public_alias,
                    specialization_id=category.specialization_id,
                    grade_id=category.grade_id,
                    grade_rank=category.grade.rank,
                    confirmed=row.profile.current_category_id is not None,
                ),
                score=VerifiedScore(total=0.0, components=(), test_percentile=None),
                category=category,
                skills=extras.skills.get(row.profile.id, []),
                privacy=extras.privacy.get(row.profile.id),
                experiences=extras.experiences.get(row.profile.id, []),
                session=extras.sessions.get(row.profile.id),
                micro_tasks=micro_tasks.get(row.profile.id, []),
            )
            member.fsp = fsp_standing(
                fsp_links.get(row.profile.id),
                fsp_achievements.get(row.profile.id, []),
                visible=bool(member.privacy and member.privacy.show_fsp_achievements),
                today=now.date(),
            )
            self._fill_facts(member)
            self._fill_micro_tasks(member, now)
            member.score = compute_verified_score(
                member.facts,
                peers.get(category.id, []) if member.facts.confirmed else [],
                await self.band(category),
                now,
                micro_tasks=member.facts.micro_score,
                fsp=member.facts.fsp_score,
            )
            members.append(member)
        return members

    @staticmethod
    def _effective_category(
        row: PoolRow, categories: dict[tuple[int, int], Category]
    ) -> Category | None:
        """Категория, присвоенная тестом, а если её нет — заявленная в опросе."""
        if row.profile.current_category is not None:
            return row.profile.current_category
        if row.claimed_specialization_id is None or row.claimed_grade_id is None:
            return None
        return categories.get((row.claimed_specialization_id, row.claimed_grade_id))

    @staticmethod
    def _fill_micro_tasks(member: PoolMember, now: datetime) -> None:
        """Фактор M: свежие оценённые микрозадачи с затуханием давности."""
        results = [
            GradedResult(
                score=assignment.score or 0.0,
                graded_at=assignment.graded_at,
                title=task.title,
                kind=task.kind.value,
            )
            for assignment, task in member.micro_tasks
            if assignment.graded_at is not None
        ]
        fresh = freshness(results, now)
        facts = member.facts
        facts.micro_score = fresh.value
        facts.micro_count = fresh.count
        if fresh.last is not None:
            facts.micro_last_title = fresh.last.title
            facts.micro_last_score = fresh.last.score
            facts.micro_last_at = fresh.last.graded_at

    @staticmethod
    def _fill_facts(member: PoolMember) -> None:
        """Переносит профиль, навыки, приватность и тест в факты подбора."""
        profile = member.row.profile
        privacy = member.privacy
        facts = member.facts
        facts.skills = {
            skill.id: SkillFact(
                skill_id=skill.id,
                slug=skill.slug,
                name=skill.name,
                verified=candidate_skill.is_verified,
                source=candidate_skill.source,
                self_level=candidate_skill.self_level,
            )
            for candidate_skill, skill in member.skills
        }
        if facts.confirmed and member.session is not None and member.session.finished_at:
            facts.test = AssessmentFact(
                session_id=member.session.id,
                theta=member.session.theta,
                se=member.session.theta_se,
                finished_at=member.session.finished_at,
                express=member.session.mode is AssessmentMode.EXPRESS,
            )
        facts.salary_expectation = profile.salary_expectation_from
        facts.salary_gross = profile.salary_expectation_gross
        facts.salary_visible = bool(privacy and privacy.show_salary_expectation)
        facts.work_formats = frozenset(profile.work_formats)
        facts.city = profile.city
        facts.city_visible = bool(privacy and privacy.show_city)
        facts.relocation_ready = profile.relocation_ready
        facts.experience_years = profile.experience_years
        facts.search_status = profile.search_status
        facts.email_verified = member.row.email_verified
        facts.completeness = profile_completeness(
            profile, len(member.skills), len(member.experiences)
        )
        facts.text = " ".join(
            [profile.about] + [f"{job.position}. {job.description}" for job in member.experiences]
        )
        fsp = member.fsp
        facts.fsp_state = fsp.state
        facts.fsp_score = fsp.score.value
        best = fsp.score.best
        if best is not None and best.result_status is not FspResultStatus.PARTICIPANT:
            facts.fsp_best = describe_result(best)
        facts.fsp_summary = summarize(fsp.score) if fsp.score.events else None


def members_by_id(members: Sequence[PoolMember]) -> dict[uuid.UUID, PoolMember]:
    """Кандидаты пула по идентификатору профиля."""
    return {member.candidate_id: member for member in members}
