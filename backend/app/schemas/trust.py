import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.employer import TrustLevel
from app.models.trust import ComplaintReason, ComplaintStatus, ComplaintTarget


class ComplaintCreate(BaseModel):
    """Жалоба кандидата на приглашение, вакансию или компанию."""

    target_type: ComplaintTarget
    target_id: uuid.UUID
    reason: ComplaintReason
    comment: str = Field(default="", max_length=1000)


class ComplaintRead(BaseModel):
    """Жалоба глазами автора."""

    id: uuid.UUID
    target_type: ComplaintTarget
    target_id: uuid.UUID
    reason: ComplaintReason
    comment: str
    status: ComplaintStatus
    resolution_note: str
    created_at: datetime


class CompanyReputationRead(BaseModel):
    """Репутация компании для кандидата: факты, а не непрозрачный балл."""

    response_rate: float | None = Field(description="Доля откликов, на которые компания ответила")
    acceptance_rate: float | None = Field(description="Доля принятых приглашений из отвеченных")
    complaints_confirmed: int
    on_platform_since: datetime
    summary: str


class SalaryCheckRead(BaseModel):
    """Вилка относительно открытых ожиданий кандидатов той же категории."""

    status: Literal["ok", "below_market", "suspicious", "unknown"]
    median: int | None = Field(description="Медиана ожиданий до вычета НДФЛ")
    message: str


class ModerationCompanyBrief(BaseModel):
    """Компания в очереди модерации."""

    id: uuid.UUID
    name: str
    inn: str | None
    trust_level: TrustLevel
    restricted_at: datetime | None
    restriction_reason: str


class ModerationComplaintRead(ComplaintRead):
    """Жалоба для модератора: с компанией, объектом и автором под псевдонимом."""

    company: ModerationCompanyBrief
    target_title: str
    author_alias: str | None


class ComplaintResolve(BaseModel):
    """Решение модератора по жалобе."""

    status: Literal[ComplaintStatus.CONFIRMED, ComplaintStatus.REJECTED]
    note: str = Field(default="", max_length=1000)


class ModerationCompanyRead(ModerationCompanyBrief):
    """Компания с сигналами для модератора."""

    complaints_open: int
    complaints_confirmed: int
    reputation: CompanyReputationRead
    suspicious_vacancies: list[str] = Field(description="Вакансии с вилкой в разы выше рынка")
    created_at: datetime


class RestrictRequest(BaseModel):
    """Ограничение компании на время проверки."""

    reason: str = Field(min_length=5, max_length=300)


class TrustLevelUpdate(BaseModel):
    """Смена уровня доверия: от него зависят квоты приглашений и вакансий."""

    trust_level: TrustLevel
