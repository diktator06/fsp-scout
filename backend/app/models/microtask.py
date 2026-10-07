import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum


class MicroTaskKind(StrEnum):
    """Вид микрозадачи (ТЗ §2): решить её или предложить подход к решению."""

    SOLVE = "solve"
    APPROACH = "approach"


class MicroTaskStatus(StrEnum):
    """Статус задачи у работодателя: архивную больше не предлагают кандидатам."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class AssignmentStatus(StrEnum):
    """Статус задачи у конкретного кандидата."""

    ASSIGNED = "assigned"
    SUBMITTED = "submitted"
    GRADED = "graded"
    EXPIRED = "expired"
    SKIPPED = "skipped"


ACTIVE_ASSIGNMENT_STATUSES = (AssignmentStatus.ASSIGNED,)


class MicroTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Короткая задача от работодателя.

    «Решить» проверяет система по эталону (число или вариант), «предложить подход»
    оценивает работодатель по рубрике — так договорились с менторами ФСП. Эталон
    хранится только здесь и в ответы API кандидату не попадает.
    """

    __tablename__ = "microtasks"
    __table_args__ = (
        CheckConstraint("time_limit_minutes BETWEEN 5 AND 240", name="time_limit_range"),
        Index("ix_microtasks_specialization_status", "specialization_id", "status"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("specializations.id", ondelete="RESTRICT")
    )
    kind: Mapped[MicroTaskKind] = mapped_column(pg_enum(MicroTaskKind, "microtask_kind"))
    title: Mapped[str] = mapped_column(String(200))
    statement: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default="[]")
    answer_key: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    rubric: Mapped[str] = mapped_column(Text, default="", server_default="")
    time_limit_minutes: Mapped[int] = mapped_column(SmallInteger, default=20, server_default="20")
    status: Mapped[MicroTaskStatus] = mapped_column(
        pg_enum(MicroTaskStatus, "microtask_status"),
        default=MicroTaskStatus.ACTIVE,
        server_default=MicroTaskStatus.ACTIVE.value,
    )


class MicroTaskAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Задача, выданная кандидату. Одну и ту же задачу кандидат получает один раз."""

    __tablename__ = "microtask_assignments"
    __table_args__ = (
        UniqueConstraint("task_id", "candidate_id"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 1)", name="score_range"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_range"),
        Index("ix_microtask_assignments_candidate_status", "candidate_id", "status"),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("microtasks.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE")
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        pg_enum(AssignmentStatus, "microtask_assignment_status"),
        default=AssignmentStatus.ASSIGNED,
        server_default=AssignmentStatus.ASSIGNED.value,
    )
    assigned_at: Mapped[datetime]
    due_at: Mapped[datetime]
    submitted_at: Mapped[datetime | None]
    answer: Mapped[str] = mapped_column(Text, default="", server_default="")
    score: Mapped[float | None] = mapped_column(Float)
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    feedback: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    graded_at: Mapped[datetime | None]
    graded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
