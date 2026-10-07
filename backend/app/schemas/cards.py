import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.assessment import AssessmentMode
from app.models.candidate import SearchStatus
from app.models.dictionary import SkillKind
from app.models.invitation import DisclosureReason, InvitationStatus
from app.schemas.dictionary import CategoryRead

GradeStatusLiteral = Literal["confirmed", "unconfirmed"]


class ScoreComponentRead(BaseModel):
    """Фактор балла: значение 0..1, вес и вклад в итог."""

    key: str
    label: str
    value: float
    weight: float
    contribution: float


class VerifiedScoreRead(BaseModel):
    """Индекс подтверждённого профиля (0–100) — ранг внутри категории."""

    total: float = Field(ge=0, le=100)
    components: list[ScoreComponentRead]
    test_percentile: int | None = Field(description="Перцентиль θ среди подтверждённых коллег")


class CardSkill(BaseModel):
    """Навык в карточке."""

    id: int
    name: str
    kind: SkillKind
    verified: bool
    self_level: int | None


class CardCompetency(BaseModel):
    """Результат теста по компетенции."""

    code: str
    name: str
    answered: int
    correct: float


class CardTest(BaseModel):
    """Сводка теста, присвоившего категорию."""

    finished_at: datetime
    mode: AssessmentMode
    items: int
    percentile: int | None
    competencies: list[CardCompetency]


class CardExperience(BaseModel):
    """Место работы. Название компании — только если кандидат разрешил его показывать."""

    position: str
    company_name: str | None
    started_on: date
    ended_on: date | None
    description: str


class FspSummary(BaseModel):
    """Блок ФСП. Пока ФСП ID не привязан, это нейтральное пустое состояние, а не минус."""

    linked: bool
    message: str


class CandidateAnonymousCard(BaseModel):
    """Обезличенная карточка кандидата.

    Контактных полей (ФИО, email, телефон, Telegram) в этой схеме нет физически:
    их невозможно случайно отдать работодателю сериализацией. Контакты приходят
    отдельным объектом `DisclosedContacts` и только после согласия кандидата.
    """

    candidate_id: uuid.UUID
    alias: str
    category: CategoryRead
    grade_status: GradeStatusLiteral
    verified_score: VerifiedScoreRead
    skills: list[CardSkill]
    experience_years: float | None
    work_formats: list[str]
    relocation_ready: bool
    city: str | None
    salary_expectation: int | None
    salary_gross: bool
    search_status: SearchStatus
    about: str
    experiences: list[CardExperience]
    test: CardTest | None
    fsp: FspSummary
    updated_at: datetime


class DisclosedContacts(BaseModel):
    """Контакты кандидата: только каналы, которые он разрешил раскрывать."""

    full_name: str | None
    email: str | None
    phone: str | None
    telegram: str | None
    disclosed_at: datetime
    reason: DisclosureReason


class InvitationBrief(BaseModel):
    """Последнее приглашение компании кандидату — для метки в выдаче."""

    id: uuid.UUID
    status: InvitationStatus
    created_at: datetime
