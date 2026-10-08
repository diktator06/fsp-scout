import uuid
from dataclasses import dataclass

SALARY_TOLERANCE = 1.1
SALARY_LIMIT = 1.3
MIN_MUST_COVERAGE = 0.5
PERSONAL_INCOME_TAX = 0.13
STRONG_BAND_POSITION = 0.5


@dataclass(frozen=True, slots=True)
class VacancyTruth:
    """Разметка вакансии экспертом: то, что работодателю нужно на самом деле."""

    vacancy_id: str
    specialization: str
    grade_ranks: frozenset[int]
    must: frozenset[str]
    nice: frozenset[str]
    salary_to_gross: float
    work_formats: frozenset[str]
    city: str | None


@dataclass(frozen=True, slots=True)
class CandidateTruth:
    """«Истина» о синтетическом кандидате. Подбор её не видит — только анкету и тест."""

    candidate_id: uuid.UUID
    specialization: str
    grade_rank: int
    skills: frozenset[str]
    salary_gross: float
    work_formats: frozenset[str]
    city: str
    relocation_ready: bool
    band_position: float = 0.0


def to_gross(amount: float, gross: bool) -> float:
    """Сумма до вычета НДФЛ: вилки и ожидания сравниваются в одной налоговой базе."""
    return amount if gross else amount / (1 - PERSONAL_INCOME_TAX)


def format_compatible(vacancy: VacancyTruth, candidate: CandidateTruth) -> bool:
    """Подходит ли кандидату формат работы, включая город для офиса и гибрида."""
    shared = vacancy.work_formats & candidate.work_formats
    if not shared:
        return False
    if shared == {"remote"} or vacancy.city is None:
        return True
    same_city = candidate.city.strip().lower() == vacancy.city.strip().lower()
    return same_city or candidate.relocation_ready


def relevance(vacancy: VacancyTruth, candidate: CandidateTruth) -> int:
    """Релевантность пары по истинным атрибутам: от 0 (не подходит) до 3 (лучший выбор).

    1 — частично: та же специализация, грейд соседний или закрыта хотя бы половина
    обязательных навыков, ожидания не выше вилки больше чем на 30 %, формат совместим.
    2 — подходит: истинный грейд из вакансии, есть все обязательные навыки, ожидания
    не выше вилки больше чем на 10 %, формат совместим.
    3 — подходит и силён: как 2, плюс истинная способность в верхней половине своего
    грейда. Это требование ТЗ «внутри категории выше те, у кого сильнее подтверждённый
    профиль»; силу система не видит, только оценку теста.
    Иначе 0. Правило записано до прогона и не подстраивалось под результаты.
    """
    if candidate.specialization != vacancy.specialization:
        return 0
    grade_gap = min((abs(candidate.grade_rank - rank) for rank in vacancy.grade_ranks), default=0)
    if grade_gap > 1 or not format_compatible(vacancy, candidate):
        return 0
    coverage = len(vacancy.must & candidate.skills) / len(vacancy.must) if vacancy.must else 1.0
    if coverage < MIN_MUST_COVERAGE:
        return 0
    if candidate.salary_gross > vacancy.salary_to_gross * SALARY_LIMIT:
        return 0
    full = (
        grade_gap == 0
        and coverage == 1.0
        and candidate.salary_gross <= vacancy.salary_to_gross * SALARY_TOLERANCE
    )
    if not full:
        return 1
    return 3 if candidate.band_position >= STRONG_BAND_POSITION else 2
