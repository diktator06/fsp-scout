import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.models.dictionary import Category


class SearchStatus(StrEnum):
    """Готовность кандидата к предложениям. «Не ищу» скрывает профиль из банка."""

    ACTIVE = "active"
    OPEN = "open"
    NOT_LOOKING = "not_looking"


class WorkFormat(StrEnum):
    """Формат работы."""

    OFFICE = "office"
    HYBRID = "hybrid"
    REMOTE = "remote"


class SkillSource(StrEnum):
    """Откуда навык попал в профиль: от этого зависит, насколько ему доверяет подбор."""

    PROFILE = "profile"
    SURVEY = "survey"
    RESUME = "resume"
    TEST = "test"
    MICRO_TASK = "micro_task"


class ContactChannel(StrEnum):
    """Каналы связи, которые раскрываются работодателю после согласия кандидата."""

    EMAIL = "email"
    PHONE = "phone"
    TELEGRAM = "telegram"


_EMPTY_ARRAY = text("'{}'::varchar[]")


def default_revealed_channels() -> list[str]:
    """Каналы, раскрываемые по умолчанию: email и Telegram, без телефона."""
    return [ContactChannel.EMAIL.value, ContactChannel.TELEGRAM.value]


class CandidateProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Профиль кандидата.

    Контактные поля (ФИО, телефон, Telegram) работодатель видит только после
    раскрытия контактов. Обезличенная карточка строится из `public_alias` и
    подтверждённых данных. Категорию выставляет только сервис оценки.
    """

    __tablename__ = "candidate_profiles"
    __table_args__ = (
        CheckConstraint(
            "salary_expectation_from IS NULL OR salary_expectation_from > 0",
            name="salary_positive",
        ),
        CheckConstraint(
            "experience_years IS NULL OR (experience_years >= 0 AND experience_years <= 60)",
            name="experience_range",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    public_alias: Mapped[str] = mapped_column(String(8), unique=True)
    full_name: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    telegram: Mapped[str | None] = mapped_column(String(64))
    city: Mapped[str | None] = mapped_column(String(120))
    about: Mapped[str] = mapped_column(Text, default="", server_default="")
    experience_years: Mapped[float | None] = mapped_column(Float)
    team_roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default=_EMPTY_ARRAY
    )
    soft_skills: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default=_EMPTY_ARRAY
    )
    work_formats: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)), default=list, server_default=_EMPTY_ARRAY
    )
    relocation_ready: Mapped[bool] = mapped_column(default=False, server_default=false())
    salary_expectation_from: Mapped[int | None] = mapped_column(Integer)
    salary_expectation_gross: Mapped[bool] = mapped_column(default=True, server_default=true())
    search_status: Mapped[SearchStatus] = mapped_column(
        pg_enum(SearchStatus, "search_status"),
        default=SearchStatus.OPEN,
        server_default=SearchStatus.OPEN.value,
    )
    current_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    grade_assigned_at: Mapped[datetime | None]

    current_category: Mapped[Category | None] = relationship(lazy="raise")


class CandidateSkill(Base):
    """Навык кандидата. `is_verified` ставят тест или микрозадача, а не сам кандидат."""

    __tablename__ = "candidate_skills"
    __table_args__ = (
        CheckConstraint("self_level IS NULL OR self_level BETWEEN 1 AND 5", name="level_range"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    self_level: Mapped[int | None] = mapped_column(SmallInteger)
    years: Mapped[float | None] = mapped_column(Float)
    source: Mapped[SkillSource] = mapped_column(pg_enum(SkillSource, "skill_source"))
    is_verified: Mapped[bool] = mapped_column(default=False, server_default=false())
    verified_at: Mapped[datetime | None]


class WorkExperience(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Место работы. Названия компаний видны работодателю, только если кандидат это разрешил."""

    __tablename__ = "work_experiences"
    __table_args__ = (
        CheckConstraint("ended_on IS NULL OR ended_on >= started_on", name="period_order"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    company_name: Mapped[str] = mapped_column(String(200))
    position: Mapped[str] = mapped_column(String(200))
    started_on: Mapped[date] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")


class Education(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Образование."""

    __tablename__ = "educations"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    institution: Mapped[str] = mapped_column(String(300))
    degree: Mapped[str] = mapped_column(String(200), default="", server_default="")
    graduated_year: Mapped[int | None] = mapped_column(SmallInteger)


class PrivacySettings(TimestampMixin, Base):
    """Что видит работодатель до раскрытия контактов и какие каналы раскрываются после.

    Публикацию в банке кандидатов включает не флаг здесь, а отдельное согласие
    `bank_publication` из журнала согласий: так требует 152-ФЗ.
    """

    __tablename__ = "privacy_settings"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    show_salary_expectation: Mapped[bool] = mapped_column(default=True, server_default=true())
    show_city: Mapped[bool] = mapped_column(default=True, server_default=true())
    show_company_names: Mapped[bool] = mapped_column(default=False, server_default=false())
    show_fsp_achievements: Mapped[bool] = mapped_column(default=True, server_default=true())
    revealed_channels: Mapped[list[str]] = mapped_column(
        ARRAY(String(16)),
        default=default_revealed_channels,
        server_default=text("'{email,telegram}'::varchar[]"),
    )
