import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.models.candidate import SearchStatus, SkillSource
from app.models.fsp import FspState


@dataclass(frozen=True, slots=True)
class SkillFact:
    """Навык кандидата так, как его видит подбор."""

    skill_id: int
    slug: str
    name: str
    verified: bool
    source: SkillSource
    self_level: int | None


@dataclass(frozen=True, slots=True)
class AssessmentFact:
    """Тест, который присвоил кандидату текущую категорию."""

    session_id: uuid.UUID
    theta: float
    se: float
    finished_at: datetime
    express: bool


@dataclass(slots=True)
class CandidateFacts:
    """Всё, что подбор знает о кандидате.

    Поля с пометкой `*_visible` отражают настройки приватности. Скрытое кандидатом
    подбор не использует ни в баллах, ни в объяснениях: иначе по порядку выдачи можно
    было бы догадаться о том, что человек решил не показывать.
    """

    candidate_id: uuid.UUID
    alias: str
    specialization_id: int
    grade_id: int
    grade_rank: int
    confirmed: bool
    skills: dict[int, SkillFact] = field(default_factory=dict)
    test: AssessmentFact | None = None
    salary_expectation: int | None = None
    salary_gross: bool = True
    salary_visible: bool = False
    work_formats: frozenset[str] = frozenset()
    city: str | None = None
    city_visible: bool = False
    relocation_ready: bool = False
    experience_years: float | None = None
    search_status: SearchStatus = SearchStatus.OPEN
    text: str = ""
    completeness: int = 0
    email_verified: bool = False
    fsp_state: FspState = FspState.NOT_LINKED
    fsp_score: float = 0.0
    fsp_best: str | None = None
    fsp_summary: str | None = None


@dataclass(frozen=True, slots=True)
class NeedFacts:
    """Потребность работодателя в форме, удобной для подбора."""

    specialization_id: int
    grade_ranks: frozenset[int]
    must: frozenset[int]
    nice: frozenset[int]
    salary_from: int
    salary_to: int
    salary_gross: bool
    work_formats: frozenset[str]
    city: str | None
    text: str
