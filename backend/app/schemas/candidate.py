import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.candidate import ContactChannel, SearchStatus, SkillSource, WorkFormat
from app.schemas.common import ORMModel
from app.schemas.dictionary import CategoryRead, GradeBrief, SkillRead, SpecializationBrief

TeamRole = Literal["developer", "team_lead", "tech_lead", "mentor", "architect", "researcher"]
OnboardingStep = Literal["profile", "survey", "grade", "test", "done"]
GradeStatus = Literal["confirmed", "unconfirmed", "not_declared"]

_PHONE = re.compile(r"^\+?[0-9()\-\s]{7,20}$")
_TELEGRAM = re.compile(r"^@?[A-Za-z0-9_]{5,32}$")


def _clean_optional(value: str | None) -> str | None:
    """Пустая строка из формы — это «не указано»."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class CandidateSkillInput(BaseModel):
    """Навык в анкете с самооценкой уровня."""

    skill_id: int
    self_level: int | None = Field(default=None, ge=1, le=5)


class WorkExperienceInput(BaseModel):
    """Место работы."""

    company_name: str = Field(min_length=1, max_length=200)
    position: str = Field(min_length=1, max_length=200)
    started_on: date
    ended_on: date | None = None
    description: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def check_period(self) -> "WorkExperienceInput":
        """Период работы не может закончиться раньше, чем начался, и начаться в будущем."""
        if self.started_on > date.today():
            raise ValueError("Дата начала работы не может быть в будущем")
        if self.ended_on is not None and self.ended_on < self.started_on:
            raise ValueError("Дата окончания раньше даты начала")
        return self


class EducationInput(BaseModel):
    """Образование."""

    institution: str = Field(min_length=2, max_length=300)
    degree: str = Field(default="", max_length=200)
    graduated_year: int | None = Field(default=None, ge=1950, le=2035)


class CandidateProfileUpdate(BaseModel):
    """Анкета кандидата целиком: PUT заменяет все поля, списки — полностью."""

    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=32)
    telegram: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=120)
    about: str = Field(default="", max_length=3000)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    team_roles: list[TeamRole] = Field(default_factory=list, max_length=6)
    soft_skills: list[str] = Field(default_factory=list, max_length=10)
    work_formats: list[WorkFormat] = Field(default_factory=list, max_length=3)
    relocation_ready: bool = False
    salary_expectation_from: int | None = Field(default=None, gt=0, le=10_000_000)
    salary_expectation_gross: bool = Field(
        default=True, description="true — сумма до вычета НДФЛ, false — «на руки»"
    )
    search_status: SearchStatus = SearchStatus.OPEN
    skills: list[CandidateSkillInput] = Field(default_factory=list, max_length=40)
    experiences: list[WorkExperienceInput] = Field(default_factory=list, max_length=20)
    educations: list[EducationInput] = Field(default_factory=list, max_length=10)

    @field_validator("full_name", "city")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        """Убирает пробелы по краям и превращает пустую строку в «не указано»."""
        return _clean_optional(value)

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str | None) -> str | None:
        """Телефон — цифры, пробелы, скобки и дефисы, необязательный «+» в начале."""
        cleaned = _clean_optional(value)
        if cleaned is not None and not _PHONE.match(cleaned):
            raise ValueError("Укажите телефон в формате +7 999 123-45-67")
        return cleaned

    @field_validator("telegram")
    @classmethod
    def check_telegram(cls, value: str | None) -> str | None:
        """Имя пользователя Telegram: 5–32 латинских символа, цифры или «_»; храним с «@»."""
        cleaned = _clean_optional(value)
        if cleaned is None:
            return None
        if not _TELEGRAM.match(cleaned):
            raise ValueError("Ник Telegram: 5–32 латинских букв, цифр или «_»")
        return cleaned if cleaned.startswith("@") else f"@{cleaned}"

    @field_validator("soft_skills")
    @classmethod
    def clean_soft_skills(cls, value: list[str]) -> list[str]:
        """Убирает пустые и повторяющиеся софт-скиллы."""
        seen: list[str] = []
        for item in value:
            text = item.strip()[:64]
            if text and text.casefold() not in {s.casefold() for s in seen}:
                seen.append(text)
        return seen

    @field_validator("team_roles", "work_formats")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        """Убирает повторы, сохраняя порядок."""
        return list(dict.fromkeys(value))

    @field_validator("skills")
    @classmethod
    def unique_skills(cls, value: list[CandidateSkillInput]) -> list[CandidateSkillInput]:
        """Один навык — одна запись: при повторе остаётся последняя."""
        return list({item.skill_id: item for item in value}.values())


class CandidateSkillRead(BaseModel):
    """Навык в профиле."""

    skill: SkillRead
    self_level: int | None
    source: SkillSource
    is_verified: bool
    verified_at: datetime | None


class WorkExperienceRead(ORMModel):
    """Место работы."""

    id: uuid.UUID
    company_name: str
    position: str
    started_on: date
    ended_on: date | None
    description: str


class EducationRead(ORMModel):
    """Образование."""

    id: uuid.UUID
    institution: str
    degree: str
    graduated_year: int | None


class CandidateProfileRead(BaseModel):
    """Профиль кандидата глазами самого кандидата (с контактами)."""

    id: uuid.UUID
    email: str
    public_alias: str
    full_name: str | None
    phone: str | None
    telegram: str | None
    city: str | None
    about: str
    experience_years: float | None
    team_roles: list[str]
    soft_skills: list[str]
    work_formats: list[str]
    relocation_ready: bool
    salary_expectation_from: int | None
    salary_expectation_gross: bool
    search_status: SearchStatus
    category: CategoryRead | None
    grade_assigned_at: datetime | None
    skills: list[CandidateSkillRead]
    experiences: list[WorkExperienceRead]
    educations: list[EducationRead]
    completeness: int = Field(ge=0, le=100, description="Заполненность профиля в процентах")
    updated_at: datetime


class PrivacySettingsRead(ORMModel):
    """Что видит работодатель до раскрытия контактов."""

    show_salary_expectation: bool
    show_city: bool
    show_company_names: bool
    show_fsp_achievements: bool
    revealed_channels: list[ContactChannel]


class PrivacySettingsUpdate(BaseModel):
    """Изменение настроек приватности."""

    show_salary_expectation: bool
    show_city: bool
    show_company_names: bool
    show_fsp_achievements: bool
    revealed_channels: list[ContactChannel] = Field(min_length=1, max_length=3)

    @field_validator("revealed_channels")
    @classmethod
    def unique_channels(cls, value: list[ContactChannel]) -> list[ContactChannel]:
        """Убирает повторы каналов."""
        return list(dict.fromkeys(value))


class ConsentsRead(BaseModel):
    """Состояние согласий кандидата."""

    personal_data_processing: bool
    bank_publication: bool
    bank_publication_granted_at: datetime | None


class CandidateStatusRead(BaseModel):
    """Где кандидат находится на пути к категории."""

    onboarding_step: OnboardingStep
    profile_completed: bool
    survey_completed: bool
    grade_status: GradeStatus = Field(
        description="confirmed — категория подтверждена тестом; unconfirmed — заявлена в опросе, "
        "но не подтверждена; not_declared — опрос не пройден"
    )
    category: CategoryRead | None
    claimed_category: CategoryRead | None
    active_session_id: uuid.UUID | None
    bank_published: bool
    completeness: int


class ResumeSkillDraft(BaseModel):
    """Навык из резюме и фрагмент, где он найден."""

    skill: SkillRead
    evidence: str


class ResumeExperienceDraft(BaseModel):
    """Место работы из резюме: черновик, который кандидат проверит перед сохранением."""

    position: str
    company_name: str
    started_on: date | None
    ended_on: date | None
    description: str


class ResumeEducationDraft(BaseModel):
    """Учебное заведение из резюме: черновик для анкеты."""

    institution: str
    degree: str
    graduated_year: int | None


class ResumeDraftRead(BaseModel):
    """Результат автораспознавания резюме. Ничего не сохраняется, пока кандидат не подтвердит."""

    full_name: str | None
    email: str | None
    phone: str | None
    telegram: str | None
    city: str | None
    experience_years: float | None
    grade: GradeBrief | None
    specialization: SpecializationBrief | None
    skills: list[ResumeSkillDraft]
    soft_skills: list[str]
    team_roles: list[TeamRole]
    experiences: list[ResumeExperienceDraft]
    about: str | None = Field(description="Раздел «О себе»")
    educations: list[ResumeEducationDraft]
    work_formats: list[WorkFormat]
    relocation_ready: bool | None = Field(
        description="Готовность к переезду; null — в резюме не указано"
    )
    evidence: dict[str, str]
    warnings: list[str]
