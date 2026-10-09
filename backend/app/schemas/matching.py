import uuid
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.candidate import WorkFormat
from app.models.matching import NeedStatus, ShortlistMarkKind, SkillImportance
from app.schemas.cards import (
    CandidateAnonymousCard,
    DisclosedContacts,
    InvitationBrief,
    ScoreComponentRead,
)
from app.schemas.dictionary import CategoryRead, GradeBrief, SkillRead, SpecializationBrief

MAX_SALARY_SPREAD = 2


def check_salary_range(salary_from: int, salary_to: int) -> None:
    """Вилка «от–до»: обе границы, «от» не больше «до», и не шире чем вдвое.

    Слишком широкая вилка («от 50 000 до 500 000») ничего не говорит кандидату,
    поэтому такие значения отклоняются уже на входе (docs/MATCHING.md, раздел 8).
    """
    if salary_from > salary_to:
        raise ValueError("Нижняя граница вилки больше верхней")
    if salary_to > salary_from * MAX_SALARY_SPREAD:
        raise ValueError("Вилка слишком широкая: верхняя граница больше нижней больше чем вдвое")


class NeedParseRequest(BaseModel):
    """Свободное описание потребности для разбора."""

    text: str = Field(min_length=20, max_length=5000)


class NeedSkillDraft(BaseModel):
    """Навык, найденный в тексте, с фрагментом-обоснованием."""

    skill: SkillRead
    importance: SkillImportance
    evidence: str | None


class NeedDraft(BaseModel):
    """Черновик потребности из разбора текста. Работодатель проверяет его перед сохранением."""

    title: str | None
    raw_text: str
    specialization: SpecializationBrief | None
    specialization_confidence: float
    grades: list[GradeBrief]
    experience_years_min: float | None
    skills: list[NeedSkillDraft]
    work_formats: list[WorkFormat]
    city: str | None
    salary_from: int | None
    salary_to: int | None
    salary_gross: bool | None
    evidence: dict[str, str]


class NeedSkillInput(BaseModel):
    """Навык потребности."""

    skill_id: int
    importance: SkillImportance = SkillImportance.MUST


class NeedCreate(BaseModel):
    """Потребность работодателя. Вилка обязательна."""

    title: str = Field(min_length=3, max_length=200, examples=["Python-разработчик в платежи"])
    raw_text: str = Field(default="", max_length=5000)
    team_description: str = Field(default="", max_length=3000)
    specialization_id: int
    grade_ids: list[int] = Field(min_length=1, max_length=4)
    skills: list[NeedSkillInput] = Field(default_factory=list, max_length=25)
    work_formats: list[WorkFormat] = Field(default_factory=list, max_length=3)
    city: str | None = Field(default=None, max_length=120)
    salary_from: int = Field(gt=0, le=10_000_000)
    salary_to: int = Field(gt=0, le=10_000_000)
    salary_gross: bool = True

    @field_validator("title", "team_description", "raw_text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Убирает пробелы по краям."""
        return value.strip()

    @field_validator("city")
    @classmethod
    def clean_city(cls, value: str | None) -> str | None:
        """Пустой город — «не важно»."""
        return (value or "").strip() or None

    @field_validator("grade_ids", "work_formats")
    @classmethod
    def unique(cls, value: list[int]) -> list[int]:
        """Убирает повторы, сохраняя порядок."""
        return list(dict.fromkeys(value))

    @field_validator("skills")
    @classmethod
    def unique_skills(cls, value: list[NeedSkillInput]) -> list[NeedSkillInput]:
        """Один навык — одна запись; при повторе остаётся более строгая важность."""
        merged: dict[int, NeedSkillInput] = {}
        for item in value:
            previous = merged.get(item.skill_id)
            if previous is None or item.importance is SkillImportance.MUST:
                merged[item.skill_id] = item
        return list(merged.values())

    @model_validator(mode="after")
    def check_salary(self) -> Self:
        """Проверка вилки."""
        check_salary_range(self.salary_from, self.salary_to)
        return self


class NeedSkillRead(BaseModel):
    """Навык потребности со справочными данными."""

    skill: SkillRead
    importance: SkillImportance


class NeedRead(BaseModel):
    """Потребность работодателя."""

    id: uuid.UUID
    title: str
    raw_text: str
    team_description: str
    specialization: SpecializationBrief
    grades: list[GradeBrief]
    skills: list[NeedSkillRead]
    work_formats: list[WorkFormat]
    city: str | None
    salary_from: int
    salary_to: int
    salary_gross: bool
    status: NeedStatus
    latest_version: int
    invitations_sent: int
    created_at: datetime
    updated_at: datetime


class CategorySliceRead(BaseModel):
    """Рекомендованная категория с рыночным срезом."""

    category: CategoryRead
    relation: str = Field(description="target, adjacent_grade или adjacent_specialization")
    candidates: int
    confirmed: int
    covering_must: int
    strong_matches: int
    median_expectation: int | None
    within_budget: bool | None


class ShortlistFilters(BaseModel):
    """Уточнения подборки. Каждое применение создаёт новую версию."""

    confirmed_only: bool = False
    expand_grades: bool = Field(
        default=False, description="Добавить соседние грейды (с понижающим множителем)"
    )
    verified_skill_ids: list[int] = Field(
        default_factory=list, max_length=10, description="Навыки, подтверждённые тестом"
    )
    required_skill_ids: list[int] = Field(default_factory=list, max_length=10)
    work_formats: list[WorkFormat] = Field(default_factory=list, max_length=3)
    city: str | None = Field(default=None, max_length=120)
    within_budget: bool = Field(default=False, description="Только с ожиданиями в вилке")
    fsp_only: bool = Field(default=False, description="Только с подтверждёнными участиями в ФСП")
    min_score: float = Field(default=0.0, ge=0, le=1)
    limit: int = Field(default=50, ge=5, le=200)


class ExplanationItemRead(BaseModel):
    """Причина в блоке «Почему в подборке»."""

    kind: str = Field(description="plus, minus или info")
    text: str


class SkillBrief(BaseModel):
    """Навык: идентификатор и название."""

    id: int
    name: str


class SkillMatchRead(BaseModel):
    """Как кандидат закрывает навык потребности."""

    skill: SkillBrief
    importance: SkillImportance
    status: str = Field(description="verified, declared, related или missing")
    via: SkillBrief | None


class MatchRead(BaseModel):
    """Балл соответствия потребности с разложением и объяснением."""

    score: float = Field(ge=0, le=100)
    components: list[ScoreComponentRead]
    penalties: list[str]
    skills: list[SkillMatchRead]
    explanation: list[ExplanationItemRead]


class ShortlistEntryRead(BaseModel):
    """Кандидат в подборке."""

    rank: int
    card: CandidateAnonymousCard
    match: MatchRead
    mark: ShortlistMarkKind | None
    note: str
    outside_filters: bool
    contacts: DisclosedContacts | None
    invitation: InvitationBrief | None


class ShortlistStats(BaseModel):
    """Сколько кандидатов было в пуле, прошло фильтры и попало в подборку."""

    pool: int
    after_filters: int
    shown: int
    autofilled: bool = Field(
        default=False, description="Точного грейда мало — добавлены соседние грейды"
    )


class ShortlistRead(BaseModel):
    """Версия подборки."""

    version: int
    versions: list[int]
    created_at: datetime
    algorithm_version: str
    filters: ShortlistFilters
    stats: ShortlistStats
    entries: list[ShortlistEntryRead]


class MarkUpdate(BaseModel):
    """Отметка кандидата в потребности."""

    mark: ShortlistMarkKind
    note: str = Field(default="", max_length=500)


class CandidateCardRead(BaseModel):
    """Карточка кандидата для работодателя.

    `card` всегда обезличена. `contacts` заполняются, только если кандидат раскрыл их
    этой компании. `match` есть, если карточку открыли из подборки потребности.
    """

    card: CandidateAnonymousCard
    contacts: DisclosedContacts | None
    match: MatchRead | None
    invitation: InvitationBrief | None


class BankSort(StrEnum):
    """Порядок банка кандидатов."""

    SCORE = "score"
    RECENT = "recent"
    EXPERIENCE = "experience"


class BankFilters(BaseModel):
    """Фильтры банка кандидатов."""

    specialization_id: int | None = None
    grade_id: int | None = None
    category_id: int | None = None
    skill_ids: list[int] = Field(default_factory=list, max_length=10)
    verified_skills_only: bool = False
    confirmed_only: bool = False
    work_format: WorkFormat | None = None
    city: str | None = Field(default=None, max_length=120)
    has_fsp: bool = False
    sort: BankSort = BankSort.SCORE


class BankCandidateRead(BaseModel):
    """Кандидат в выдаче банка."""

    card: CandidateAnonymousCard
    contacts_disclosed: bool
    invitation: InvitationBrief | None


class BankPage(BaseModel):
    """Страница банка с общим числом и разбивкой по статусу грейда."""

    items: list[BankCandidateRead]
    total: int
    confirmed: int
    unconfirmed: int
    limit: int
    offset: int
