import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.crud import (
    hiring_need_crud,
    invitation_crud,
    need_skill_crud,
    shortlist_crud,
    skill_lookup_crud,
    specialization_crud,
)
from app.crud.candidate_search import PoolQuery
from app.models.matching import HiringNeed, NeedStatus, SkillImportance
from app.models.user import User
from app.schemas.dictionary import CategoryRead, GradeBrief, SkillRead, SpecializationBrief
from app.schemas.matching import (
    CategorySliceRead,
    NeedCreate,
    NeedDraft,
    NeedRead,
    NeedSkillDraft,
    NeedSkillRead,
)
from app.services.employer.company_service import CompanyService
from app.services.matching.candidate_pool import CandidatePoolService
from app.services.matching.category_recommender import category_targets, market_slices
from app.services.matching.engine import MatchingEngine
from app.services.matching.need_parser import CatalogGrade, parse_need_text


def _now() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(UTC)


class NeedService:
    """Потребности работодателя: разбор текста, сохранение и рекомендованные категории."""

    def __init__(self, session: AsyncSession, clock: Callable[[], datetime] = _now) -> None:
        """Получает сессию БД и источник времени."""
        self._session = session
        self._clock = clock
        self._companies = CompanyService(session, clock)
        self._engine = MatchingEngine(session)

    async def parse(self, user: User, text: str) -> NeedDraft:
        """Черновик потребности из свободного текста. Ничего не сохраняет."""
        await self._companies.require_recruiter(user)
        catalog = await self._engine.catalog()
        grades = [CatalogGrade(id=g.id, code=g.code, rank=g.rank) for g in catalog.grades]
        parsed = parse_need_text(text, catalog.skills, grades)
        skills_by_id = {skill.id: skill for skill in catalog.skills}
        specialization = None
        if parsed.specialization_code:
            found = await specialization_crud.get_by_code(self._session, parsed.specialization_code)
            specialization = SpecializationBrief.model_validate(found) if found else None
        grade_by_code = {grade.code: grade for grade in catalog.grades}
        title = parsed.title
        if title is None and specialization is not None:
            grade_names = [
                grade_by_code[code].name for code in parsed.grade_codes if code in grade_by_code
            ]
            title = (
                f"{specialization.name} · {', '.join(grade_names)}"
                if grade_names
                else specialization.name
            )
        return NeedDraft(
            title=title,
            raw_text=text,
            specialization=specialization,
            specialization_confidence=parsed.specialization_confidence,
            grades=[
                GradeBrief.model_validate(grade_by_code[code])
                for code in parsed.grade_codes
                if code in grade_by_code
            ],
            experience_years_min=parsed.experience_years_min,
            skills=[
                NeedSkillDraft(
                    skill=SkillRead(
                        id=item.skill_id,
                        slug=skills_by_id[item.skill_id].slug,
                        name=skills_by_id[item.skill_id].name,
                        kind=skills_by_id[item.skill_id].kind,
                        aliases=list(skills_by_id[item.skill_id].aliases),
                    ),
                    importance=SkillImportance(item.importance),
                    evidence=item.evidence,
                )
                for item in parsed.skills
            ],
            work_formats=parsed.work_formats,
            city=parsed.city,
            salary_from=parsed.salary_from,
            salary_to=parsed.salary_to,
            salary_gross=parsed.salary_gross,
            evidence=parsed.evidence,
        )

    async def create(self, user: User, payload: NeedCreate) -> NeedRead:
        """Сохраняет потребность. Первую версию подборки строит сервис подборок."""
        recruiter = await self._companies.require_recruiter(user)
        await self._validate(payload)
        need = await hiring_need_crud.create(
            self._session,
            {
                **payload.model_dump(exclude={"skills"}),
                "company_id": recruiter.company_id,
                "created_by": user.id,
                "work_formats": [item.value for item in payload.work_formats],
            },
        )
        await need_skill_crud.replace_for_need(
            self._session, need.id, {item.skill_id: item.importance for item in payload.skills}
        )
        await self._session.commit()
        return await self.get(user, need.id)

    async def update(self, user: User, need_id: uuid.UUID, payload: NeedCreate) -> NeedRead:
        """Изменяет потребность. Старые версии подборки остаются как были."""
        need = await self._owned(user, need_id, for_update=True)
        await self._validate(payload)
        await hiring_need_crud.update(
            self._session,
            need,
            {
                **payload.model_dump(exclude={"skills"}),
                "work_formats": [item.value for item in payload.work_formats],
            },
        )
        await need_skill_crud.replace_for_need(
            self._session, need.id, {item.skill_id: item.importance for item in payload.skills}
        )
        await self._session.commit()
        return await self.get(user, need.id)

    async def set_status(self, user: User, need_id: uuid.UUID, status: NeedStatus) -> NeedRead:
        """Закрывает потребность или возвращает её в работу."""
        need = await self._owned(user, need_id, for_update=True)
        await hiring_need_crud.update(self._session, need, {"status": status})
        await self._session.commit()
        return await self.get(user, need.id)

    async def list_needs(self, user: User) -> list[NeedRead]:
        """Потребности компании, от новых к старым."""
        recruiter = await self._companies.require_recruiter(user)
        needs = await hiring_need_crud.list_for_company(self._session, recruiter.company_id)
        return [await self._view(need) for need in needs]

    async def get(self, user: User, need_id: uuid.UUID) -> NeedRead:
        """Потребность компании."""
        return await self._view(await self._owned(user, need_id))

    async def categories(self, user: User, need_id: uuid.UUID) -> list[CategorySliceRead]:
        """Рекомендованные категории с рыночным срезом: «сначала рынок, потом люди».

        Срез показывает, сколько кандидатов в целевой и соседних категориях, сколько
        из них закрывают обязательный стек и реалистична ли вилка.
        """
        need = await self._owned(user, need_id)
        catalog = await self._engine.catalog()
        context = await self._engine.context(need)
        targets = category_targets(
            context.facts,
            catalog.specialization_codes[need.specialization_id],
            [(grade.id, grade.rank) for grade in catalog.grades],
            catalog.specialization_ids,
        )
        pool_service = CandidatePoolService(self._session, self._clock)
        members = await pool_service.load(
            PoolQuery(specialization_ids=sorted({target.specialization_id for target in targets}))
        )
        scored = await self._engine.score(context, members)
        slices = market_slices(
            context.facts, targets, [(item.member.facts, item.result.score) for item in scored]
        )
        categories = await pool_service.categories()
        return [
            CategorySliceRead(
                category=CategoryRead.model_validate(
                    categories[(item.target.specialization_id, item.target.grade_id)]
                ),
                relation=item.target.relation,
                candidates=item.candidates,
                confirmed=item.confirmed,
                covering_must=item.covering_must,
                strong_matches=item.strong_matches,
                median_expectation=item.median_expectation,
                within_budget=item.within_budget,
            )
            for item in slices
            if (item.target.specialization_id, item.target.grade_id) in categories
        ]

    async def _owned(
        self, user: User, need_id: uuid.UUID, *, for_update: bool = False
    ) -> HiringNeed:
        """Потребность компании пользователя или 404."""
        recruiter = await self._companies.require_recruiter(user)
        need = await hiring_need_crud.get_for_company(
            self._session, need_id, recruiter.company_id, for_update=for_update
        )
        if need is None:
            raise NotFoundError("Потребность не найдена")
        return need

    async def _validate(self, payload: NeedCreate) -> None:
        """Справочные ссылки потребности существуют."""
        if await specialization_crud.get(self._session, payload.specialization_id) is None:
            raise DomainValidationError(
                "Специализация не найдена", details={"field": "specialization_id"}
            )
        catalog = await self._engine.catalog()
        known_grades = {grade.id for grade in catalog.grades}
        if set(payload.grade_ids) - known_grades:
            raise DomainValidationError("Грейд не найден", details={"field": "grade_ids"})
        skill_ids = [item.skill_id for item in payload.skills]
        missing = sorted(
            set(skill_ids) - await skill_lookup_crud.existing_ids(self._session, skill_ids)
        )
        if missing:
            raise DomainValidationError(
                "Указаны несуществующие навыки", details={"skill_ids": missing}
            )

    async def _view(self, need: HiringNeed) -> NeedRead:
        """Потребность для ответа API."""
        catalog = await self._engine.catalog()
        grades = {grade.id: grade for grade in catalog.grades}
        skills = await need_skill_crud.list_with_skills(self._session, [need.id])
        invitations = await invitation_crud.list_for_company(
            self._session, need.company_id, need_id=need.id
        )
        return NeedRead(
            id=need.id,
            title=need.title,
            raw_text=need.raw_text,
            team_description=need.team_description,
            specialization=SpecializationBrief.model_validate(need.specialization),
            grades=[
                GradeBrief.model_validate(grades[grade_id])
                for grade_id in sorted(need.grade_ids, key=lambda gid: grades[gid].rank)
                if grade_id in grades
            ],
            skills=[
                NeedSkillRead(skill=SkillRead.model_validate(skill), importance=item.importance)
                for item, skill in skills
            ],
            work_formats=need.work_formats,
            city=need.city,
            salary_from=need.salary_from,
            salary_to=need.salary_to,
            salary_gross=need.salary_gross,
            status=need.status,
            latest_version=await shortlist_crud.latest_version(self._session, need.id),
            invitations_sent=len(invitations),
            created_at=need.created_at,
            updated_at=need.updated_at,
        )
