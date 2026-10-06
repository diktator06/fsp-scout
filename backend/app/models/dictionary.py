from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    Identity,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import pg_enum

SKILL_EMBEDDING_DIMENSIONS = 384


class SkillKind(StrEnum):
    """Тип навыка: от него зависит, как навык показывается в опросе и учитывается в подборе."""

    LANGUAGE = "language"
    FRAMEWORK = "framework"
    DATABASE = "database"
    TOOL = "tool"
    CONCEPT = "concept"
    SOFT = "soft"


class Industry(Base):
    """Отрасль (финтех, e-commerce, госсектор…): используется в опросе кандидата."""

    __tablename__ = "industries"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")


class Specialization(TimestampMixin, Base):
    """ИТ-специализация (backend, frontend, …), первая ось категории кандидата.

    `direction_*` — IT-направление, которое ТЗ называет «отраслью» (уточнение менторов):
    «Разработка», «Данные и ML», «Качество», «Инфраструктура». По нему группируется
    выбор специализации в опросе.
    """

    __tablename__ = "specializations"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    direction_code: Mapped[str] = mapped_column(
        String(32), default="development", server_default="development"
    )
    direction_name: Mapped[str] = mapped_column(
        String(64), default="Разработка", server_default="Разработка"
    )
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")


class Grade(Base):
    """Грейд, вторая ось категории. `rank` задаёт порядок: Intern < Junior < Middle < Senior."""

    __tablename__ = "grades"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    rank: Mapped[int] = mapped_column(SmallInteger, unique=True)
    experience_hint: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    default_theta_cut: Mapped[float] = mapped_column(Float)


class Category(Base):
    """Категория = специализация × грейд.

    Именно её видит работодатель. Порог `theta_cut` по шкале способностей IRT
    задаётся на уровне категории: для разных специализаций пороги могут разойтись
    после калибровки.
    """

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("specialization_id", "grade_id"),)

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("specializations.id", ondelete="CASCADE"), index=True
    )
    grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id", ondelete="RESTRICT"))
    code: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    theta_cut: Mapped[float] = mapped_column(Float)

    specialization: Mapped[Specialization] = relationship(lazy="raise")
    grade: Mapped[Grade] = relationship(lazy="raise")


class Skill(TimestampMixin, Base):
    """Навык из единого справочника.

    Алиасы нужны, чтобы «питон», «Python 3» и «py» считались одним навыком.
    """

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[SkillKind] = mapped_column(pg_enum(SkillKind, "skill_kind"))
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(String(128)), default=list, server_default=text("'{}'::varchar[]")
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(SKILL_EMBEDDING_DIMENSIONS))


class SpecializationSkill(Base):
    """Насколько навык типичен для специализации (0..1).

    Из этих весов собираются варианты стека в опросе кандидата.
    """

    __tablename__ = "specialization_skills"
    __table_args__ = (
        CheckConstraint("typical_weight >= 0 AND typical_weight <= 1", name="weight_range"),
    )

    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("specializations.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    typical_weight: Mapped[float] = mapped_column(Float, default=0.5, server_default="0.5")
