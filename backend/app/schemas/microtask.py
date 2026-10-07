import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.microtask import AssignmentStatus, MicroTaskKind, MicroTaskStatus

AnswerFormat = Literal["number", "choice", "text"]


class MicroTaskCreate(BaseModel):
    """Микрозадача работодателя.

    «Решить» требует эталон: число с допуском или номер верного варианта — его
    проверяет система. «Предложить подход» требует рубрику: по ней оценивает
    работодатель, и кандидат видит её заранее.
    """

    kind: MicroTaskKind
    title: str = Field(min_length=3, max_length=200)
    statement: str = Field(min_length=20, max_length=5000)
    specialization_id: int
    options: list[str] = Field(default_factory=list, max_length=6)
    answer_value: float | None = Field(default=None, description="Эталонное число для «решить»")
    answer_tolerance: float = Field(default=0.0, ge=0)
    correct_option: int | None = Field(default=None, ge=0, description="Номер верного варианта")
    rubric: str = Field(default="", max_length=2000)
    time_limit_minutes: int = Field(default=20, ge=5, le=240)

    @field_validator("title", "statement", "rubric")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Убирает пробелы по краям."""
        return value.strip()

    @field_validator("options")
    @classmethod
    def clean_options(cls, value: list[str]) -> list[str]:
        """Пустые варианты отбрасываются."""
        return [item.strip() for item in value if item.strip()]

    @model_validator(mode="after")
    def check_key(self) -> Self:
        """У «решить» должен быть эталон, у «предложить подход» — рубрика."""
        if self.kind is MicroTaskKind.SOLVE:
            if self.options:
                if len(self.options) < 2:
                    raise ValueError("Для выбора нужно хотя бы два варианта")
                if self.correct_option is None or self.correct_option >= len(self.options):
                    raise ValueError("Отметьте верный вариант")
            elif self.answer_value is None:
                raise ValueError("Укажите эталонный ответ — число или варианты с верным")
        elif len(self.rubric) < 10:
            raise ValueError("Опишите, по каким критериям оцените подход")
        return self


class TaskStatsRead(BaseModel):
    """Статистика задачи у работодателя."""

    assigned: int
    answered: int
    graded: int
    awaiting_review: int
    average_score: float | None


class MicroTaskRead(BaseModel):
    """Задача глазами работодателя — вместе с эталоном и статистикой."""

    id: uuid.UUID
    kind: MicroTaskKind
    title: str
    statement: str
    specialization_id: int
    specialization_name: str
    options: list[str]
    answer_value: float | None
    answer_tolerance: float
    correct_option: int | None
    rubric: str
    time_limit_minutes: int
    status: MicroTaskStatus
    created_at: datetime
    stats: TaskStatsRead


class AssignedTaskRead(BaseModel):
    """Задача глазами кандидата: эталона здесь нет физически."""

    id: uuid.UUID
    kind: MicroTaskKind
    title: str
    statement: str
    options: list[str]
    rubric: str
    answer_format: AnswerFormat
    time_limit_minutes: int
    company_name: str


class AssignmentRead(BaseModel):
    """Выданная кандидату задача и результат по ней."""

    id: uuid.UUID
    status: AssignmentStatus
    assigned_at: datetime
    due_at: datetime
    submitted_at: datetime | None
    answer: str
    score: float | None
    rating: int | None
    feedback: str
    graded_at: datetime | None
    task: AssignedTaskRead


class FreshnessRead(BaseModel):
    """Фактор M: актуальность профиля по свежим микрозадачам."""

    value: float = Field(ge=0, le=1)
    vps_points: float = Field(description="Вклад в индекс подтверждённого профиля, баллов")
    count: int
    last_graded_at: datetime | None
    half_life_days: int


class TasksOverviewRead(BaseModel):
    """Раздел «Задачи» кандидата."""

    available: bool = Field(description="Есть ли специализация: без опроса задач не подобрать")
    current: AssignmentRead | None
    history: list[AssignmentRead]
    freshness: FreshnessRead
    can_request: bool
    requests_left: int
    next_offer_at: datetime | None


class AnswerSubmit(BaseModel):
    """Ответ кандидата: число, номер варианта или описание подхода."""

    answer: str = Field(min_length=1, max_length=5000)


class SubmissionCandidateRead(BaseModel):
    """Автор ответа для работодателя — обезличенно, как в банке."""

    candidate_id: uuid.UUID
    alias: str
    category_title: str | None
    grade_status: Literal["confirmed", "unconfirmed"] | None


class SubmissionRead(BaseModel):
    """Ответ кандидата на задачу компании."""

    id: uuid.UUID
    status: AssignmentStatus
    submitted_at: datetime | None
    answer: str
    score: float | None
    rating: int | None
    feedback: str
    graded_at: datetime | None
    candidate: SubmissionCandidateRead


class GradeRequest(BaseModel):
    """Оценка подхода работодателем по рубрике задачи."""

    rating: int = Field(ge=1, le=5)
    feedback: str = Field(default="", max_length=1000)
