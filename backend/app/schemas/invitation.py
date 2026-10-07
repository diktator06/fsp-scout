import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.candidate import WorkFormat
from app.models.employer import CompanySize, TrustLevel
from app.models.invitation import DeclineReason, InvitationStatus
from app.schemas.cards import DisclosedContacts
from app.schemas.dictionary import CategoryRead
from app.schemas.matching import check_salary_range
from app.schemas.trust import CompanyReputationRead

EventActor = Literal["employer", "candidate", "system"]


class InvitationCreate(BaseModel):
    """Приглашение кандидату: описание, вилка и способ связи обязательны (ТЗ §2.2.2)."""

    candidate_id: uuid.UUID
    need_id: uuid.UUID | None = None
    title: str = Field(min_length=3, max_length=200, examples=["Python-разработчик в платежи"])
    offer_description: str = Field(min_length=20, max_length=3000)
    salary_from: int = Field(gt=0, le=10_000_000, examples=[250_000])
    salary_to: int = Field(gt=0, le=10_000_000, examples=[320_000])
    salary_gross: bool = True
    work_format: WorkFormat
    contact_method: str = Field(
        min_length=5, max_length=300, examples=["Telegram @kedr_hr, отвечаем в течение дня"]
    )

    @field_validator("title", "offer_description", "contact_method")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """Убирает пробелы по краям."""
        return value.strip()

    @model_validator(mode="after")
    def check_salary(self) -> Self:
        """Проверка вилки."""
        check_salary_range(self.salary_from, self.salary_to)
        return self


class DeclineRequest(BaseModel):
    """Отказ от приглашения с причиной: из причин складывается обратная связь работодателю."""

    reason: DeclineReason
    comment: str = Field(default="", max_length=500)


class InvitationEventRead(BaseModel):
    """Шаг таймлайна приглашения."""

    status: InvitationStatus
    at: datetime
    actor: EventActor


class CompanyBrief(BaseModel):
    """Компания глазами кандидата: видна сразу, ещё до ответа на приглашение."""

    id: uuid.UUID
    name: str
    industry: str | None
    city: str | None
    website: str | None
    size: CompanySize | None
    description: str
    trust_level: TrustLevel
    under_review: bool = Field(description="Компания на проверке модератора после жалоб")
    reputation: CompanyReputationRead | None


class EmployerContacts(BaseModel):
    """Контакты работодателя, которые кандидат видит после принятия приглашения."""

    recruiter_name: str | None
    recruiter_position: str | None
    email: str | None
    phone: str | None
    telegram: str | None


class InvitationBase(BaseModel):
    """Общие поля приглашения для обеих сторон."""

    id: uuid.UUID
    status: InvitationStatus
    title: str
    offer_description: str
    salary_from: int
    salary_to: int
    salary_gross: bool
    work_format: WorkFormat
    contact_method: str
    decline_reason: DeclineReason | None
    decline_comment: str
    created_at: datetime
    viewed_at: datetime | None
    responded_at: datetime | None
    expires_at: datetime
    events: list[InvitationEventRead]


class CandidateInvitationRead(InvitationBase):
    """Приглашение глазами кандидата."""

    company: CompanyBrief
    recruiter_name: str | None
    employer_contacts: EmployerContacts | None


class InvitationCandidateRead(BaseModel):
    """Кандидат в приглашении глазами работодателя: псевдоним до согласия, контакты после."""

    candidate_id: uuid.UUID
    alias: str
    category: CategoryRead | None
    grade_status: Literal["confirmed", "unconfirmed"]
    contacts: DisclosedContacts | None


class EmployerInvitationRead(InvitationBase):
    """Приглашение глазами работодателя."""

    need_id: uuid.UUID | None
    need_title: str | None
    candidate: InvitationCandidateRead
