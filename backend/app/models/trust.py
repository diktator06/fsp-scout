import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum


class ComplaintTarget(StrEnum):
    """На что жалуется кандидат."""

    INVITATION = "invitation"
    VACANCY = "vacancy"
    COMPANY = "company"


class ComplaintReason(StrEnum):
    """Причина жалобы — типичные признаки фиктивной вакансии или недобросовестного работодателя."""

    FAKE_OFFER = "fake_offer"
    SALARY_MISMATCH = "salary_mismatch"
    PAYMENT_REQUEST = "payment_request"
    SPAM = "spam"
    RUDE = "rude"
    OTHER = "other"


class ComplaintStatus(StrEnum):
    """Решение модератора по жалобе."""

    OPEN = "open"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Complaint(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Жалоба кандидата на компанию, её приглашение или вакансию.

    Один кандидат жалуется на один объект один раз: иначе один человек мог бы в
    одиночку заблокировать компанию. Автоматическое ограничение считает жалобы
    разных кандидатов.
    """

    __tablename__ = "complaints"
    __table_args__ = (
        UniqueConstraint("author_user_id", "target_type", "target_id"),
        Index("ix_complaints_company_status", "company_id", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    target_type: Mapped[ComplaintTarget] = mapped_column(
        pg_enum(ComplaintTarget, "complaint_target")
    )
    target_id: Mapped[uuid.UUID]
    reason: Mapped[ComplaintReason] = mapped_column(pg_enum(ComplaintReason, "complaint_reason"))
    comment: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    status: Mapped[ComplaintStatus] = mapped_column(
        pg_enum(ComplaintStatus, "complaint_status"),
        default=ComplaintStatus.OPEN,
        server_default=ComplaintStatus.OPEN.value,
    )
    resolution_note: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None]
