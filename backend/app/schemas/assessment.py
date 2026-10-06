import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.assessment import (
    AssessmentMode,
    GradeChangeReason,
    ResponseFormat,
    SessionOutcome,
    SessionStatus,
)
from app.models.candidate import WorkFormat
from app.schemas.candidate import TeamRole
from app.schemas.dictionary import CategoryRead, GradeBrief, SpecializationBrief

IntegrityEvent = Literal["focus_lost", "paste", "fullscreen_exit"]


class SurveyCreate(BaseModel):
    """Ответы опроса: отрасль, специализация, стек, опыт и заявленный грейд."""

    specialization_id: int
    claimed_grade_id: int
    industry_ids: list[int] = Field(default_factory=list, max_length=3)
    primary_skill_ids: list[int] = Field(min_length=1, max_length=12)
    experience_years: float = Field(ge=0, le=60)
    team_roles: list[TeamRole] = Field(default_factory=list, max_length=6)
    work_formats: list[WorkFormat] = Field(default_factory=list, max_length=3)

    @field_validator("industry_ids", "primary_skill_ids", "team_roles", "work_formats")
    @classmethod
    def unique(cls, value: list[Any]) -> list[Any]:
        """Убирает повторы, сохраняя порядок."""
        return list(dict.fromkeys(value))


class SurveyRead(BaseModel):
    """Сохранённый опрос."""

    id: uuid.UUID
    specialization: SpecializationBrief
    claimed_grade: GradeBrief
    industry_ids: list[int]
    primary_skill_ids: list[int]
    experience_years: float
    team_roles: list[str]
    created_at: datetime


class BlueprintCompetency(BaseModel):
    """Компетенция в тесте и её доля."""

    code: str
    name: str
    weight: float
    bank_size: int
    included: bool = Field(description="false — компетенция отключена: в опросе нет нужного навыка")


class BlueprintRead(BaseModel):
    """Из чего будет состоять тест специализации для этого кандидата."""

    specialization: SpecializationBrief
    competencies: list[BlueprintCompetency]
    min_items: int
    max_items: int
    available: bool


class GradeOptionRead(BaseModel):
    """Можно ли сейчас пройти тест на грейд."""

    grade: GradeBrief
    allowed: bool
    reason: str
    available_at: datetime | None


class EligibilityRead(BaseModel):
    """Доступные тесты, текущая категория и незавершённая сессия."""

    express_available: bool
    current_category: CategoryRead | None
    active_session_id: uuid.UUID | None
    survey: SurveyRead | None
    options: list[GradeOptionRead]


class SessionStart(BaseModel):
    """Начало теста на выбранный грейд по последнему опросу."""

    target_grade_id: int
    mode: AssessmentMode = Field(
        default=AssessmentMode.FULL,
        description="full — полный тест (12–20 заданий), express — 6–8 заданий для демонстрации",
    )


class ItemOption(BaseModel):
    """Вариант ответа."""

    key: str
    text: str


class ItemTable(BaseModel):
    """Таблица в условии задания."""

    title: str
    columns: list[str]
    rows: list[list[Any]]


class ItemView(BaseModel):
    """Задание, как его видит кандидат. Ключа ответа здесь нет и быть не может."""

    id: uuid.UUID
    position: int
    competency: str
    competency_name: str
    prompt: str
    response_format: ResponseFormat
    options: list[ItemOption] = Field(default_factory=list)
    code: str | None = None
    code_language: str | None = None
    tables: list[ItemTable] = Field(default_factory=list)
    input_hint: str | None = None
    unit: str | None = None
    time_limit_sec: int
    deadline_at: datetime
    seconds_left: int


class AnswerSubmit(BaseModel):
    """Ответ на текущее задание: ключ варианта (a–d) или число строкой."""

    item_id: uuid.UUID
    answer: str = Field(min_length=1, max_length=64)


class IntegrityEventCreate(BaseModel):
    """Событие, которое может указывать на помощь со стороны (без блокировки теста)."""

    event: IntegrityEvent


class CompetencyResult(BaseModel):
    """Результат по компетенции."""

    code: str
    name: str
    answered: int
    correct: int


class GradeScalePoint(BaseModel):
    """Порог грейда на шкале способностей."""

    grade: GradeBrief
    theta_cut: float


class SessionResult(BaseModel):
    """Итог теста."""

    outcome: SessionOutcome
    theta: float
    theta_se: float
    items_scored: int
    target_grade: GradeBrief
    resulting_category: CategoryRead | None
    suggested_grade: GradeBrief | None
    can_accept_suggested: bool
    next_grade_unlocked: GradeBrief | None
    competencies: list[CompetencyResult]
    scale: list[GradeScalePoint]
    integrity_flags: dict[str, int]


class SessionRead(BaseModel):
    """Состояние сессии тестирования."""

    id: uuid.UUID
    status: SessionStatus
    mode: AssessmentMode
    specialization: SpecializationBrief
    target_grade: GradeBrief
    answered: int
    min_items: int
    max_items: int
    started_at: datetime
    expires_at: datetime
    finished_at: datetime | None
    current_item: ItemView | None
    result: SessionResult | None


class SessionSummaryRead(BaseModel):
    """Строка истории тестов."""

    id: uuid.UUID
    status: SessionStatus
    mode: AssessmentMode
    outcome: SessionOutcome | None
    specialization: SpecializationBrief
    target_grade: GradeBrief
    items_scored: int
    theta: float | None
    started_at: datetime
    finished_at: datetime | None


class GradeHistoryRead(BaseModel):
    """Смена категории."""

    category: CategoryRead
    reason: GradeChangeReason
    changed_at: datetime
    session_id: uuid.UUID | None


class AssessmentHistoryRead(BaseModel):
    """История тестов и смен категории."""

    sessions: list[SessionSummaryRead]
    grade_changes: list[GradeHistoryRead]
