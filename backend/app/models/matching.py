import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.models.dictionary import Specialization

_EMPTY_INT_ARRAY = text("'{}'::integer[]")
_EMPTY_VARCHAR_ARRAY = text("'{}'::varchar[]")


class NeedStatus(StrEnum):
    """Статус потребности: закрытая остаётся в истории вместе с подборками."""

    ACTIVE = "active"
    CLOSED = "closed"


class SkillImportance(StrEnum):
    """Важность навыка в потребности: must весит вдвое больше nice."""

    MUST = "must"
    NICE = "nice"


class ShortlistMarkKind(StrEnum):
    """Отметка работодателя в подборке. Переживает уточнение фильтров."""

    PINNED = "pinned"
    HIDDEN = "hidden"


class HiringNeed(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Потребность работодателя: кого ищем, на каких условиях и чем занимается команда.

    Вилка обязательна уже здесь: из потребности приглашение наследует условия, а
    подбор сравнивает их с ожиданиями кандидатов.
    """

    __tablename__ = "hiring_needs"
    __table_args__ = (
        CheckConstraint("salary_from > 0 AND salary_from <= salary_to", name="salary_range"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    raw_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    team_description: Mapped[str] = mapped_column(Text, default="", server_default="")
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
    status: Mapped[NeedStatus] = mapped_column(
        pg_enum(NeedStatus, "need_status"),
        default=NeedStatus.ACTIVE,
        server_default=NeedStatus.ACTIVE.value,
    )
    extraction: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")

    specialization: Mapped[Specialization] = relationship(lazy="raise")


class NeedSkill(Base):
    """Навык в потребности с важностью."""

    __tablename__ = "need_skills"

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hiring_needs.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    importance: Mapped[SkillImportance] = mapped_column(
        pg_enum(SkillImportance, "skill_importance")
    )


class Shortlist(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Версия подборки по потребности.

    Каждое уточнение фильтров создаёт новую версию, старые остаются для сравнения.
    Версия алгоритма записывается, чтобы выдачу можно было воспроизвести.
    """

    __tablename__ = "shortlists"
    __table_args__ = (UniqueConstraint("need_id", "version"),)

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hiring_needs.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(SmallInteger)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    algorithm_version: Mapped[str] = mapped_column(String(16))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ShortlistEntry(Base):
    """Кандидат в версии подборки: место, балл, разложение балла и объяснение."""

    __tablename__ = "shortlist_entries"

    shortlist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shortlists.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    rank: Mapped[int] = mapped_column(SmallInteger)
    match_score: Mapped[float] = mapped_column(Float)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSONB)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSONB)
    outside_filters: Mapped[bool] = mapped_column(default=False, server_default=false())


class ShortlistMark(TimestampMixin, Base):
    """Отметка «закреплён» или «скрыт» на уровне потребности, а не версии подборки."""

    __tablename__ = "shortlist_marks"

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hiring_needs.id", ondelete="CASCADE"), primary_key=True
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    mark: Mapped[ShortlistMarkKind] = mapped_column(pg_enum(ShortlistMarkKind, "shortlist_mark"))
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
