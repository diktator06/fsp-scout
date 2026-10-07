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
from app.models.dictionary import Grade
from app.models.matching import HiringNeed, SkillImportance
from app.services.matching.candidate_pool import PoolMember
from app.services.matching.explanations import ExplanationItem, explain_match
from app.services.matching.facts import NeedFacts
from app.services.matching.match_scoring import MatchResult, score_match
from app.services.matching.need_parser import CatalogSkill
from app.services.matching.text_similarity import TfidfIndex

MAX_SKILLS_IN_CATALOG = 5000
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
    """Потребность, подготовленная к подбору."""

    need: HiringNeed
    facts: NeedFacts
    text: str


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
        catalog = await self.catalog()
        need_skills = await need_skill_crud.list_with_skills(self._session, [need.id])
        must = frozenset(
            item.skill_id for item, _ in need_skills if item.importance is SkillImportance.MUST
        )
        nice = frozenset(
            item.skill_id for item, _ in need_skills if item.importance is SkillImportance.NICE
        )
        ranks = {grade.id: grade.rank for grade in catalog.grades}
        wanted = {ranks[grade_id] for grade_id in need.grade_ids if grade_id in ranks}
        text = " ".join(part for part in (need.title, need.team_description, need.raw_text) if part)
        return MatchingContext(
            need=need,
            facts=NeedFacts(
                specialization_id=need.specialization_id,
                grade_ranks=frozenset(wanted),
                must=must,
                nice=nice,
                salary_from=need.salary_from,
                salary_to=need.salary_to,
                salary_gross=need.salary_gross,
                work_formats=frozenset(need.work_formats),
                city=need.city,
                text=text,
            ),
            text=text,
        )

    async def allowed_grade_ids(self, need: HiringNeed, *, expand: bool) -> list[int]:
        """Грейды для жёсткого фильтра: из потребности и, при расширении, соседние."""
        catalog = await self.catalog()
        ranks = {grade.id: grade.rank for grade in catalog.grades}
        wanted = {ranks[grade_id] for grade_id in need.grade_ids if grade_id in ranks}
        if expand:
            wanted |= {rank + step for rank in wanted for step in (-1, 1)}
        return [grade.id for grade in catalog.grades if grade.rank in wanted]

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
