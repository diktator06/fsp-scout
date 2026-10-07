import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.candidate import WorkFormat
from app.models.matching import SkillImportance
from app.models.vacancy import ApplicationStatus, RejectReason, VacancyStatus
from app.schemas.cards import CandidateAnonymousCard, DisclosedContacts
from app.schemas.dictionary import GradeBrief, SpecializationBrief
from app.schemas.invitation import CompanyBrief, EmployerContacts
from app.schemas.matching import MatchRead, NeedSkillInput, NeedSkillRead, check_salary_range
from app.schemas.trust import SalaryCheckRead

ApplicationActor = Literal["candidate", "employer"]


class VacancyCreate(BaseModel):
    """Вакансия работодателя. Вилка «от–до» обязательна, как и в приглашении (ТЗ §2.2)."""

    title: str = Field(min_length=3, max_length=200, examples=["Python-разработчик (Middle)"])
    description: str = Field(min_length=20, max_length=8000)
    specialization_id: int
    grade_ids: list[int] = Field(min_length=1, max_length=4)
    skills: list[NeedSkillInput] = Field(default_factory=list, max_length=25)
    work_formats: list[WorkFormat] = Field(min_length=1, max_length=3)
    city: str | None = Field(default=None, max_length=120)
    salary_from: int = Field(gt=0, le=10_000_000)
    salary_to: int = Field(gt=0, le=10_000_000)
    salary_gross: bool = True
    need_id: uuid.UUID | None = None

    @field_validator("title", "description")
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
        """Проверка вилки: обе границы, «от» не больше «до», не шире чем вдвое."""
        check_salary_range(self.salary_from, self.salary_to)
        return self


class VacancyBase(BaseModel):
    """Поля вакансии, общие для работодателя и кандидата."""

    id: uuid.UUID
    title: str
    description: str
    specialization: SpecializationBrief
    grades: list[GradeBrief]
    skills: list[NeedSkillRead]
    work_formats: list[WorkFormat]
    city: str | None
    salary_from: int
    salary_to: int
    salary_gross: bool
    published_at: datetime | None


class VacancyRead(VacancyBase):
    """Вакансия глазами работодателя: статус и воронка откликов."""

    status: VacancyStatus
    need_id: uuid.UUID | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    applications_total: int
    applications_new: int
    applications_by_status: dict[ApplicationStatus, int]
    market_check: SalaryCheckRead


class ApplicationBrief(BaseModel):
    """Отклик кандидата на вакансию — для метки в списке."""

    id: uuid.UUID
    status: ApplicationStatus
    created_at: datetime


class VacancyPublicRead(VacancyBase):
    """Вакансия глазами кандидата: компания и вилка видны сразу."""

    company: CompanyBrief
    match: MatchRead | None = Field(
        description="Соответствие кандидату; нет, пока кандидат не прошёл опрос"
    )
    application: ApplicationBrief | None


class VacancyBoardPage(BaseModel):
    """Страница списка вакансий для кандидата."""

    items: list[VacancyPublicRead]
    total: int
    can_apply: bool = Field(description="Пройден ли опрос: без категории откликаться рано")


class ApplicationCreate(BaseModel):
    """Отклик кандидата. Согласие открыть контакты компании обязательно: отклик их раскрывает."""

    cover_letter: str = Field(default="", max_length=3000)
    share_contacts: bool = Field(
        description="Согласие открыть компании контакты: отклик — собственная инициатива кандидата"
    )

    @field_validator("cover_letter")
    @classmethod
    def strip_letter(cls, value: str) -> str:
        """Убирает пробелы по краям."""
        return value.strip()


class ApplicationDecision(BaseModel):
    """Решение работодателя по отклику: пригласить на собеседование или отказать с причиной."""

    status: Literal[ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED]
    reject_reason: RejectReason | None = None
    message: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def reason_for_reject(self) -> Self:
        """Отказ без причины ничего не даёт кандидату, поэтому причина обязательна."""
        if self.status is ApplicationStatus.REJECTED and self.reject_reason is None:
            raise ValueError("Укажите причину отказа: кандидат увидит её и поймёт, что подтянуть")
        return self


class ApplicationEventRead(BaseModel):
    """Шаг таймлайна отклика."""

    status: ApplicationStatus
    at: datetime
    actor: ApplicationActor


class ApplicationBase(BaseModel):
    """Общие поля отклика для обеих сторон."""

    id: uuid.UUID
    status: ApplicationStatus
    cover_letter: str
    reject_reason: RejectReason | None
    reject_comment: str
    created_at: datetime
    viewed_at: datetime | None
    responded_at: datetime | None
    events: list[ApplicationEventRead]


class VacancyBriefRead(BaseModel):
    """Вакансия в отклике кандидата."""

    id: uuid.UUID
    title: str
    status: VacancyStatus
    salary_from: int
    salary_to: int
    salary_gross: bool
    company: CompanyBrief


class CandidateApplicationRead(ApplicationBase):
    """Отклик глазами кандидата. Контакты работодателя — после приглашения на собеседование."""

    vacancy: VacancyBriefRead
    employer_contacts: EmployerContacts | None


class EmployerApplicationRead(ApplicationBase):
    """Отклик глазами работодателя: карточка, балл соответствия и контакты кандидата."""

    vacancy_id: uuid.UUID
    match_score: float | None
    card: CandidateAnonymousCard | None
    contacts: DisclosedContacts | None
