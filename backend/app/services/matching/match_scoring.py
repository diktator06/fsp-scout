from collections.abc import Mapping
from dataclasses import dataclass, field

from app.models.candidate import SkillSource, WorkFormat
from app.services.matching.facts import CandidateFacts, NeedFacts

MATCH_ALGORITHM_VERSION = "match-1.0"
MATCH_WEIGHTS = {"skills": 0.35, "verified": 0.35, "semantic": 0.15, "conditions": 0.15}
MATCH_LABELS = {
    "skills": "Навыки",
    "verified": "Подтверждённость",
    "semantic": "Близость к задачам",
    "conditions": "Условия",
}
MUST_WEIGHT = 2.0
NICE_WEIGHT = 1.0
TYPICAL_FOR_SPECIALIZATION = 0.3
NET_TO_GROSS = 1 / 0.87
SALARY_TOLERANCE = 1.3
UNKNOWN_SALARY_FIT = 0.75
UNCONFIRMED_FACTOR = 0.75
ADJACENT_GRADE_FACTOR = 0.85


@dataclass(frozen=True, slots=True)
class SkillMatch:
    """Как кандидат закрывает один навык потребности."""

    skill_id: int
    importance: str
    status: str
    credit: float
    via_skill_id: int | None = None


@dataclass(frozen=True, slots=True)
class ConditionCheck:
    """Проверка одного условия: зарплата, формат или место работы."""

    key: str
    status: str
    value: float


@dataclass(slots=True)
class MatchResult:
    """Балл соответствия потребности и всё, из чего он сложился."""

    score: float
    components: dict[str, float]
    skills: list[SkillMatch] = field(default_factory=list)
    conditions: list[ConditionCheck] = field(default_factory=list)
    penalties: list[tuple[str, float]] = field(default_factory=list)


def skill_credit(
    candidate: CandidateFacts, skill_id: int, typical_weight: float
) -> tuple[str, float]:
    """Насколько можно доверять навыку кандидата.

    1,0 — подтверждён тестом или задачей; 0,7 — заявлен и типичен для специализации
    кандидата (согласуется с категорией); 0,5 — заявлен, но для специализации нетипичен
    или взят только из резюме.
    """
    fact = candidate.skills.get(skill_id)
    if fact is None:
        return "missing", 0.0
    if fact.verified:
        return "verified", 1.0
    if fact.source is not SkillSource.RESUME and typical_weight >= TYPICAL_FOR_SPECIALIZATION:
        return "declared", 0.7
    return "declared", 0.5


def score_skills(
    need: NeedFacts,
    candidate: CandidateFacts,
    typical_weights: Mapping[int, float],
    relations: Mapping[int, Mapping[int, float]],
) -> tuple[float, list[SkillMatch]]:
    """SkillFit = Σ wₛ·cred(c, s) / Σ wₛ, где w = 2 для must и 1 для nice.

    Недостающий навык частично закрывается родственным: 0,5 × похожесть (Django за
    FastAPI). Если в потребности нет навыков, фактор нейтрален и равен 0,5.
    """
    requested = [(skill_id, "must") for skill_id in sorted(need.must)] + [
        (skill_id, "nice") for skill_id in sorted(need.nice - need.must)
    ]
    if not requested:
        return 0.5, []
    total_weight = 0.0
    earned = 0.0
    matches = []
    for skill_id, importance in requested:
        weight = MUST_WEIGHT if importance == "must" else NICE_WEIGHT
        status, credit = skill_credit(candidate, skill_id, typical_weights.get(skill_id, 0.0))
        via = None
        if status == "missing":
            related = [
                (similarity, related_id)
                for related_id, similarity in relations.get(skill_id, {}).items()
                if related_id in candidate.skills
            ]
            if related:
                similarity, via = max(related)
                status, credit = "related", 0.5 * similarity
        matches.append(SkillMatch(skill_id, importance, status, round(credit, 3), via))
        total_weight += weight
        earned += weight * credit
    return earned / total_weight, matches


def to_gross(amount: float, gross: bool) -> float:
    """Сумма до вычета НДФЛ: ожидания «на руки» и вилки «gross» сравниваются в одной базе."""
    return amount if gross else amount * NET_TO_GROSS


def salary_fit(need: NeedFacts, candidate: CandidateFacts) -> ConditionCheck:
    """1, если ожидания не выше верхней границы вилки; линейно до 0 при 1,3 × «до»."""
    if candidate.salary_expectation is None or not candidate.salary_visible:
        return ConditionCheck("salary", "unknown", UNKNOWN_SALARY_FIT)
    expectation = to_gross(candidate.salary_expectation, candidate.salary_gross)
    ceiling = to_gross(need.salary_to, need.salary_gross)
    if expectation <= ceiling:
        return ConditionCheck("salary", "ok", 1.0)
    limit = ceiling * SALARY_TOLERANCE
    if expectation >= limit:
        return ConditionCheck("salary", "mismatch", 0.0)
    return ConditionCheck("salary", "partial", round((limit - expectation) / (limit - ceiling), 3))


def format_fit(need: NeedFacts, candidate: CandidateFacts) -> ConditionCheck:
    """Совпадение формата работы. Если стороны его не указали, условие не мешает."""
    if not need.work_formats:
        return ConditionCheck("format", "ok", 1.0)
    if not candidate.work_formats:
        return ConditionCheck("format", "unknown", 0.8)
    if need.work_formats & candidate.work_formats:
        return ConditionCheck("format", "ok", 1.0)
    return ConditionCheck("format", "mismatch", 0.4)


def location_fit(need: NeedFacts, candidate: CandidateFacts) -> ConditionCheck:
    """Город важен, только если работа не полностью удалённая."""
    on_site = bool(need.work_formats) and not need.work_formats <= {WorkFormat.REMOTE.value}
    if not need.city or not on_site:
        return ConditionCheck("location", "ok", 1.0)
    if candidate.city is None or not candidate.city_visible:
        return ConditionCheck("location", "unknown", 0.8)
    if candidate.city.strip().lower() == need.city.strip().lower():
        return ConditionCheck("location", "ok", 1.0)
    if candidate.relocation_ready:
        return ConditionCheck("location", "partial", 0.9)
    return ConditionCheck("location", "mismatch", 0.5)


def score_match(
    need: NeedFacts,
    candidate: CandidateFacts,
    *,
    verified_score: float,
    semantic: float,
    typical_weights: Mapping[int, float],
    relations: Mapping[int, Mapping[int, float]],
) -> MatchResult:
    """Match = 0,35·SkillFit + 0,35·VPS/100 + 0,15·Semantic + 0,15·Conditions.

    Поверх — понижающие множители: неподтверждённый грейд опускается в выдаче (так
    просили менторы), соседний грейд при расширенном поиске — тоже. Формулы и веса —
    ARCHITECTURE_AND_PLAN.md §3.6.2, версия записывается в каждую подборку.
    """
    skills_value, skill_matches = score_skills(need, candidate, typical_weights, relations)
    conditions = [
        salary_fit(need, candidate),
        format_fit(need, candidate),
        location_fit(need, candidate),
    ]
    conditions_value = 1.0
    for check in conditions:
        conditions_value *= check.value
    components = {
        "skills": round(skills_value, 4),
        "verified": round(verified_score / 100, 4),
        "semantic": round(max(0.0, min(1.0, semantic)), 4),
        "conditions": round(conditions_value, 4),
    }
    score = sum(MATCH_WEIGHTS[key] * value for key, value in components.items())
    penalties = []
    if not candidate.confirmed:
        penalties.append(("unconfirmed_grade", UNCONFIRMED_FACTOR))
    if need.grade_ranks and candidate.grade_rank not in need.grade_ranks:
        penalties.append(("adjacent_grade", ADJACENT_GRADE_FACTOR))
    for _, factor in penalties:
        score *= factor
    return MatchResult(
        score=round(score, 4),
        components=components,
        skills=skill_matches,
        conditions=conditions,
        penalties=penalties,
    )
