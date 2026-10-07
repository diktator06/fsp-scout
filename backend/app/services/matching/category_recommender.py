import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.services.matching.facts import CandidateFacts, NeedFacts
from app.services.matching.match_scoring import to_gross

STRONG_MATCH = 0.6
MIN_FOR_MEDIAN = 3

ADJACENT_SPECIALIZATIONS: dict[str, tuple[str, ...]] = {
    "backend": ("devops",),
    "devops": ("backend",),
    "frontend": ("mobile",),
    "mobile": ("frontend",),
    "data_analytics": ("ml",),
    "ml": ("data_analytics",),
    "qa": (),
}


@dataclass(frozen=True, slots=True)
class CategoryTarget:
    """Категория, которую стоит показать работодателю, и её связь с потребностью."""

    specialization_id: int
    grade_id: int
    grade_rank: int
    relation: str


@dataclass(frozen=True, slots=True)
class CategorySlice:
    """Рыночный срез по категории: сколько людей, сколько сильных, сколько они хотят."""

    target: CategoryTarget
    candidates: int
    confirmed: int
    covering_must: int
    strong_matches: int
    median_expectation: int | None
    within_budget: bool | None


def category_targets(
    need: NeedFacts,
    specialization_code: str,
    grades: Sequence[tuple[int, int]],
    specialization_ids: Mapping[str, int],
) -> list[CategoryTarget]:
    """Целевые категории потребности и соседние: грейд ±1 и смежная специализация.

    `grades` — пары (id, rank). Смежная специализация показывается только с теми же
    грейдами: рекомендация должна расширять поиск, а не уводить в сторону.
    """
    ranks = {rank: grade_id for grade_id, rank in grades}
    targets: list[CategoryTarget] = []
    wanted = sorted(need.grade_ranks)
    for rank in wanted:
        targets.append(CategoryTarget(need.specialization_id, ranks[rank], rank, "target"))
    neighbours = {rank + step for rank in wanted for step in (-1, 1)} - set(wanted)
    for rank in sorted(neighbours):
        if rank in ranks:
            targets.append(
                CategoryTarget(need.specialization_id, ranks[rank], rank, "adjacent_grade")
            )
    for code in ADJACENT_SPECIALIZATIONS.get(specialization_code, ()):
        spec_id = specialization_ids.get(code)
        if spec_id is None:
            continue
        for rank in wanted:
            targets.append(CategoryTarget(spec_id, ranks[rank], rank, "adjacent_specialization"))
    return targets


def market_slices(
    need: NeedFacts,
    targets: Sequence[CategoryTarget],
    pool: Sequence[tuple[CandidateFacts, float]],
) -> list[CategorySlice]:
    """Срез по каждой категории из пула кандидатов с их баллами соответствия.

    Медиана ожиданий считается только по открытым кандидатами ожиданиям, приведённым
    к базе вилки (до вычета НДФЛ или на руки). Она показывается, если таких ожиданий
    не меньше трёх: агрегат по одному-двум людям фактически раскрыл бы их цифры.
    """
    slices = []
    for target in targets:
        members = [
            (facts, score)
            for facts, score in pool
            if facts.specialization_id == target.specialization_id
            and facts.grade_id == target.grade_id
        ]
        expectations = [
            to_gross(facts.salary_expectation, facts.salary_gross)
            for facts, _ in members
            if facts.salary_expectation is not None and facts.salary_visible
        ]
        median = None
        within = None
        if len(expectations) >= MIN_FOR_MEDIAN:
            gross_median = statistics.median(expectations)
            median_in_need_basis = gross_median if need.salary_gross else gross_median * 0.87
            median = round(median_in_need_basis / 1000) * 1000
            within = median <= need.salary_to
        covering = sum(1 for facts, _ in members if need.must and need.must <= set(facts.skills))
        slices.append(
            CategorySlice(
                target=target,
                candidates=len(members),
                confirmed=sum(1 for facts, _ in members if facts.confirmed),
                covering_must=covering,
                strong_matches=sum(1 for _, score in members if score >= STRONG_MATCH),
                median_expectation=median,
                within_budget=within,
            )
        )
    return slices
