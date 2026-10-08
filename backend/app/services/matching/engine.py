from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    candidate_pool_crud,
    grade_crud,
    need_skill_crud,
    skill_crud,
    specialization_crud,
)
from app.crud.candidate_search import PoolQuery
from app.models.dictionary import Grade
from app.models.matching import HiringNeed, SkillImportance
from app.services.matching.candidate_pool import CandidatePoolService, PoolMember
from app.services.matching.explanations import ExplanationItem, explain_match
from app.services.matching.facts import NeedFacts
from app.services.matching.match_scoring import MatchResult, score_match
from app.services.matching.need_parser import CatalogSkill
from app.services.matching.text_similarity import TfidfIndex

MAX_SKILLS_IN_CATALOG = 5000
AUTOFILL_MIN_POOL = 10
SHARED_TERMS = 4
MIN_SHARED_SIMILARITY = 0.12


@dataclass(slots=True)
class SkillCatalog:
    """Справочник навыков для подбора: поиск в тексте, синонимы, веса и родственные навыки."""

    skills: list[CatalogSkill]
    names: dict[int, str]
    synonyms: dict[str, str]
    typical_weights: dict[tuple[int, int], float]
    relations: dict[int, dict[int, float]]
    specialization_codes: dict[int, str]
    specialization_ids: dict[str, int]
    grades: list[Grade] = field(default_factory=list)

    def weights_for(self, specialization_id: int) -> dict[int, float]:
        """Насколько каждый навык типичен для специализации."""
        return {
            skill_id: weight
            for (spec_id, skill_id), weight in self.typical_weights.items()
            if spec_id == specialization_id
        }


@dataclass(slots=True)
class MatchingContext:
    """Потребность или вакансия, подготовленная к подбору."""

    facts: NeedFacts
    text: str


@dataclass(slots=True)
class PoolSelection:
    """Кандидаты для подборки и признак того, что добавлены соседние грейды."""

    members: list[PoolMember]
    autofilled: bool


@dataclass(slots=True)
class ScoredMember:
    """Кандидат с баллом соответствия и объяснением."""

    member: PoolMember
    result: MatchResult
    explanation: list[ExplanationItem]


class MatchingEngine:
    """Связывает чистые модули подбора с данными: каталог, контекст потребности, оценку пула."""

    def __init__(self, session: AsyncSession) -> None:
        """Получает сессию БД."""
        self._session = session
        self._catalog: SkillCatalog | None = None

    async def catalog(self) -> SkillCatalog:
        """Справочник навыков со связями; загружается один раз на запрос."""
        if self._catalog is not None:
            return self._catalog
        skills = await skill_crud.get_multi(self._session, limit=MAX_SKILLS_IN_CATALOG)
        specializations = await specialization_crud.list_all(self._session)
        codes = {item.id: item.code for item in specializations}
        weights = await candidate_pool_crud.specialization_skill_weights(self._session, codes)
        relations = await candidate_pool_crud.skill_relations(self._session)
        by_skill: dict[int, dict[str, float]] = {}
        for (spec_id, skill_id), weight in weights.items():
            by_skill.setdefault(skill_id, {})[codes[spec_id]] = weight
        synonyms: dict[str, str] = {}
        for skill in skills:
            for variant in (skill.slug, skill.name, *skill.aliases):
                key = variant.strip().lower()
                if len(key) >= 2 and " " not in key:
                    synonyms.setdefault(key, skill.slug)
        self._catalog = SkillCatalog(
            skills=[
                CatalogSkill(
                    id=skill.id,
                    slug=skill.slug,
                    name=skill.name,
                    kind=skill.kind,
                    aliases=tuple(skill.aliases),
                    specialization_weights=by_skill.get(skill.id, {}),
                )
                for skill in skills
            ],
            names={skill.id: skill.name for skill in skills},
            synonyms=synonyms,
            typical_weights=weights,
            relations=relations,
            specialization_codes=codes,
            specialization_ids={code: spec_id for spec_id, code in codes.items()},
            grades=list(await grade_crud.list_all(self._session)),
        )
        return self._catalog

    async def context(self, need: HiringNeed) -> MatchingContext:
        """Потребность в форме для подбора: навыки по важности, допустимые грейды, текст."""
        need_skills = await need_skill_crud.list_with_skills(self._session, [need.id])
        return await self.build_context(
            specialization_id=need.specialization_id,
            grade_ids=need.grade_ids,
            skills=[(item.skill_id, item.importance) for item, _ in need_skills],
            salary_from=need.salary_from,
            salary_to=need.salary_to,
            salary_gross=need.salary_gross,
            work_formats=need.work_formats,
            city=need.city,
            texts=(need.title, need.team_description, need.raw_text),
        )

    async def build_context(
        self,
        *,
        specialization_id: int,
        grade_ids: Sequence[int],
        skills: Sequence[tuple[int, SkillImportance]],
        salary_from: int,
        salary_to: int,
        salary_gross: bool,
        work_formats: Sequence[str],
        city: str | None,
        texts: Sequence[str],
    ) -> MatchingContext:
        """Контекст подбора из полей потребности или вакансии: правила у них общие."""
        catalog = await self.catalog()
        ranks = {grade.id: grade.rank for grade in catalog.grades}
        wanted = {ranks[grade_id] for grade_id in grade_ids if grade_id in ranks}
        text = " ".join(part for part in texts if part)
        return MatchingContext(
            facts=NeedFacts(
                specialization_id=specialization_id,
                grade_ranks=frozenset(wanted),
                must=frozenset(skill for skill, kind in skills if kind is SkillImportance.MUST),
                nice=frozenset(skill for skill, kind in skills if kind is SkillImportance.NICE),
                salary_from=salary_from,
                salary_to=salary_to,
                salary_gross=salary_gross,
                work_formats=frozenset(work_formats),
                city=city,
                text=text,
            ),
            text=text,
        )

    async def allowed_grade_ids(self, need: HiringNeed, *, expand: bool) -> list[int]:
        """Грейды для жёсткого фильтра: из потребности и, при расширении, соседние."""
        return await self.grade_filter(need.grade_ids, expand=expand)

    async def grade_filter(self, grade_ids: Sequence[int], *, expand: bool) -> list[int]:
        """Грейды для жёсткого фильтра по списку грейдов потребности или вакансии."""
        catalog = await self.catalog()
        ranks = {grade.id: grade.rank for grade in catalog.grades}
        wanted = {ranks[grade_id] for grade_id in grade_ids if grade_id in ranks}
        if expand:
            wanted |= {rank + step for rank in wanted for step in (-1, 1)}
        return [grade.id for grade in catalog.grades if grade.rank in wanted]

    async def select_pool(
        self,
        pool: CandidatePoolService,
        specialization_id: int,
        grade_ids: Sequence[int],
        *,
        expand: bool,
    ) -> PoolSelection:
        """Кандидаты для подборки: точный грейд, а если их меньше десяти — и соседние.

        Тест ошибается в основном на соседний грейд, поэтому часть подходящих людей
        оказывается рядом с запрошенным. Пока точных кандидатов хватает, выдача из них и
        состоит; когда их мало, соседние грейды добавляются с понижающим множителем и
        пометкой — точный грейд остаётся наверху. Решение принято по оценке подбора на
        размеченных парах (docs/VALIDATION.md).
        """
        allowed = await self.grade_filter(grade_ids, expand=expand)
        members = await pool.load(
            PoolQuery(specialization_ids=[specialization_id], grade_ids=allowed)
        )
        if expand or len(members) >= AUTOFILL_MIN_POOL:
            return PoolSelection(members=members, autofilled=False)
        wider = await self.grade_filter(grade_ids, expand=True)
        if set(wider) == set(allowed):
            return PoolSelection(members=members, autofilled=False)
        members = await pool.load(
            PoolQuery(specialization_ids=[specialization_id], grade_ids=wider)
        )
        return PoolSelection(members=members, autofilled=True)

    async def score(
        self, context: MatchingContext, members: Sequence[PoolMember]
    ) -> list[ScoredMember]:
        """Балл соответствия и объяснение для каждого кандидата пула.

        Индекс TF-IDF строится по текстам этого же пула: редкие для специализации слова
        (платежи, геоданные) весят больше общих (разработка, команда).
        """
        catalog = await self.catalog()
        index = TfidfIndex(
            [member.facts.text for member in members] + [context.text], catalog.synonyms
        )
        scored = []
        for member in members:
            similarity = (
                index.similarity(member.facts.text, context.text) if member.facts.text else 0.0
            )
            result = score_match(
                context.facts,
                member.facts,
                verified_score=member.score.total,
                semantic=similarity,
                typical_weights=catalog.weights_for(member.facts.specialization_id),
                relations=catalog.relations,
            )
            shared = (
                index.shared_terms(member.facts.text, context.text, SHARED_TERMS)
                if similarity >= MIN_SHARED_SIMILARITY
                else []
            )
            explanation = explain_match(
                result,
                member.facts,
                member.score,
                skill_names=catalog.names,
                category_title=member.category.title,
                grade_name=member.category.grade.name,
                shared_terms=shared,
            )
            scored.append(ScoredMember(member=member, result=result, explanation=explanation))
        scored.sort(key=lambda item: item.result.score, reverse=True)
        return scored
