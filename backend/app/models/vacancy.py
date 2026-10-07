import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.models.matching import SkillImportance

_EMPTY_INT_ARRAY = text("'{}'::integer[]")
_EMPTY_VARCHAR_ARRAY = text("'{}'::varchar[]")


class VacancyStatus(StrEnum):
    """Статус вакансии: черновик не виден кандидатам, закрытая остаётся в истории откликов."""

    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class ApplicationStatus(StrEnum):
    """Статусы отклика. Переходы задаёт автомат в `services/vacancies/state_machine.py`."""

    SUBMITTED = "submitted"
    VIEWED = "viewed"
    INTERVIEW = "interview"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


ACTIVE_APPLICATION_STATUSES = (ApplicationStatus.SUBMITTED, ApplicationStatus.VIEWED)


class RejectReason(StrEnum):
    """Причина отказа по отклику: кандидат видит её и понимает, что подтянуть."""

    SKILLS = "skills"
    GRADE = "grade"
    SALARY = "salary"
    POSITION_FILLED = "position_filled"
    OTHER = "other"


class Vacancy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Вакансия, опубликованная работодателем напрямую.

    Дополнительный канал к основной механике: кандидат, которого ещё не пригласили,
    может проявить инициативу сам. Вилка «от–до» обязательна, как и в приглашении.
    """

    __tablename__ = "vacancies"
    __table_args__ = (
        CheckConstraint("salary_from > 0 AND salary_from <= salary_to", name="salary_range"),
        Index("ix_vacancies_status_published", "status", "published_at"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    need_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hiring_needs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("specializations.id", ondelete="RESTRICT")
    )
    grade_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default=_EMPTY_INT_ARRAY
    )
    work_formats: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), default=list, server_default=_EMPTY_VARCHAR_ARRAY
    )
    city: Mapped[str | None] = mapped_column(String(120))
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    salary_gross: Mapped[bool] = mapped_column(default=True, server_default=true())
    status: Mapped[VacancyStatus] = mapped_column(
        pg_enum(VacancyStatus, "vacancy_status"),
        default=VacancyStatus.DRAFT,
        server_default=VacancyStatus.DRAFT.value,
    )
    published_at: Mapped[datetime | None]
    closed_at: Mapped[datetime | None]


class VacancySkill(Base):
    """Навык вакансии с важностью: must весит вдвое больше nice, как в потребности."""

    __tablename__ = "vacancy_skills"

    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    importance: Mapped[SkillImportance] = mapped_column(
        pg_enum(SkillImportance, "skill_importance")
    )


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Отклик кандидата на вакансию.

    Отклик — собственная инициатива кандидата, поэтому он сразу открывает компании
    его контакты (правило ТЗ §2.2). На одну вакансию кандидат откликается один раз.
    """

    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("vacancy_id", "candidate_id"),)

    vacancy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vacancies.id", ondelete="CASCADE"), index=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    cover_letter: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status"),
        default=ApplicationStatus.SUBMITTED,
        server_default=ApplicationStatus.SUBMITTED.value,
        index=True,
    )
    match_score: Mapped[float | None] = mapped_column(Float)
    reject_reason: Mapped[RejectReason | None] = mapped_column(
        pg_enum(RejectReason, "reject_reason")
    )
    reject_comment: Mapped[str] = mapped_column(String(500), default="", server_default="")
    viewed_at: Mapped[datetime | None]
    responded_at: Mapped[datetime | None]


class ApplicationEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Журнал переходов отклика: из него строится таймлайн у обеих сторон."""

    __tablename__ = "application_events"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(
        pg_enum(ApplicationStatus, "application_status")
    )
    to_status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
