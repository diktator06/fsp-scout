import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Float,
    ForeignKey,
    Identity,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.models.dictionary import Grade


class ResponseFormat(StrEnum):
    """Формат ответа на задание."""

    SINGLE_CHOICE = "single_choice"
    NUMERIC = "numeric"


class ItemFamilyStatus(StrEnum):
    """Жизненный цикл семейства заданий.

    `pilot` — показывается без влияния на результат, копит ответы для калибровки.
    `active` — участвует в оценке. `compromised` — отключено детектором утечек.
    """

    DRAFT = "draft"
    PILOT = "pilot"
    ACTIVE = "active"
    COMPROMISED = "compromised"
    RETIRED = "retired"


class ItemOrigin(StrEnum):
    """Кто подготовил семейство: эксперт или эксперт вместе с LLM-черновиком."""

    EXPERT = "expert"
    LLM_ASSISTED = "llm_assisted"


class SessionStatus(StrEnum):
    """Состояние сессии тестирования."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    EXPIRED = "expired"


class SessionOutcome(StrEnum):
    """Итог теста на заявленный грейд."""

    PASSED_CONFIDENT = "passed_confident"
    PASSED = "passed"
    FAILED = "failed"


class GradeChangeReason(StrEnum):
    """Почему у кандидата сменилась категория."""

    INITIAL = "initial"
    UPGRADE = "upgrade"
    DOWNGRADE_VOLUNTARY = "downgrade_voluntary"
    ACCEPTED_LOWER = "accepted_lower"


_EMPTY_VARCHAR_ARRAY = text("'{}'::varchar[]")


class Competency(Base):
    """Ось содержания теста (Python, SQL, алгоритмы, статистика…).

    Компетенции общие для специализаций: SQL проверяется и у бэкендеров, и у
    аналитиков одними и теми же семействами. Веса задаёт blueprint специализации.
    `gate_skill_slugs` — навыки, без которых компетенция в тест не входит:
    Java-разработчик не должен получать задания на особенности Python.
    """

    __tablename__ = "competencies"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    gate_skill_slugs: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default=_EMPTY_VARCHAR_ARRAY
    )
    verifies_skill_slugs: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default=_EMPTY_VARCHAR_ARRAY
    )


class SpecializationCompetency(Base):
    """Вес компетенции в тесте специализации (blueprint)."""

    __tablename__ = "specialization_competencies"
    __table_args__ = (CheckConstraint("weight > 0 AND weight <= 1", name="weight_range"),)

    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("specializations.id", ondelete="CASCADE"), primary_key=True
    )
    competency_id: Mapped[int] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"), primary_key=True
    )
    weight: Mapped[float] = mapped_column(Float)


class ItemFamily(TimestampMixin, Base):
    """Параметрическое семейство заданий, единица калибровки IRT.

    Экземпляры одного семейства различаются данными, но не ходом решения. Поэтому
    параметры `a` (дискриминативность), `b` (сложность) и `c` (угадывание) общие
    для всех экземпляров. Структуру семейства задаёт код генератора, а здесь
    хранятся калиброванные параметры, статус и статистика показов.
    """

    __tablename__ = "item_families"
    __table_args__ = (
        CheckConstraint("irt_a > 0", name="discrimination_positive"),
        CheckConstraint("irt_c >= 0 AND irt_c < 1", name="guessing_range"),
        CheckConstraint("time_limit_sec BETWEEN 15 AND 900", name="time_limit_range"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    competency_id: Mapped[int] = mapped_column(
        ForeignKey("competencies.id", ondelete="RESTRICT"), index=True
    )
    response_format: Mapped[ResponseFormat] = mapped_column(
        pg_enum(ResponseFormat, "response_format")
    )
    nominal_grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id", ondelete="RESTRICT"))
    irt_a: Mapped[float] = mapped_column(Float)
    irt_b: Mapped[float] = mapped_column(Float)
    irt_c: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    time_limit_sec: Mapped[int] = mapped_column(SmallInteger)
    status: Mapped[ItemFamilyStatus] = mapped_column(
        pg_enum(ItemFamilyStatus, "item_family_status")
    )
    origin: Mapped[ItemOrigin] = mapped_column(
        pg_enum(ItemOrigin, "item_origin"),
        default=ItemOrigin.EXPERT,
        server_default=ItemOrigin.EXPERT.value,
    )
    exposure_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    responses_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    correct_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    version: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    calibrated_at: Mapped[datetime | None]

    competency: Mapped[Competency] = relationship(lazy="raise")
    nominal_grade: Mapped[Grade] = relationship(lazy="raise")


class SurveyResponse(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Ответы опроса: специализация, стек, опыт и заявленный грейд.

    Сам опрос категорию не даёт. Он выбирает специализацию и blueprint теста и
    заполняет профиль.
    """

    __tablename__ = "survey_responses"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("specializations.id", ondelete="RESTRICT")
    )
    claimed_grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id", ondelete="RESTRICT"))
    industry_ids: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), default=list, server_default=text("'{}'::smallint[]")
    )
    primary_skill_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), default=list, server_default=text("'{}'::integer[]")
    )
    experience_years: Mapped[float] = mapped_column(Float)
    team_roles: Mapped[list[str]] = mapped_column(
        ARRAY(String(32)), default=list, server_default=_EMPTY_VARCHAR_ARRAY
    )
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    survey_version: Mapped[str] = mapped_column(String(16))


class AssessmentSession(UUIDPrimaryKeyMixin, Base):
    """Сессия адаптивного теста на заявленный грейд."""

    __tablename__ = "assessment_sessions"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    survey_response_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("survey_responses.id", ondelete="RESTRICT")
    )
    specialization_id: Mapped[int] = mapped_column(
        ForeignKey("specializations.id", ondelete="RESTRICT")
    )
    target_grade_id: Mapped[int] = mapped_column(ForeignKey("grades.id", ondelete="RESTRICT"))
    status: Mapped[SessionStatus] = mapped_column(pg_enum(SessionStatus, "session_status"))
    seed_salt: Mapped[str] = mapped_column(String(32))
    blueprint: Mapped[dict[str, float]] = mapped_column(JSONB)
    pilot_positions: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), default=list, server_default=text("'{}'::smallint[]")
    )
    theta: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    theta_se: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    items_scored: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    outcome: Mapped[SessionOutcome | None] = mapped_column(
        pg_enum(SessionOutcome, "session_outcome")
    )
    resulting_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    suggested_grade_id: Mapped[int | None] = mapped_column(
        ForeignKey("grades.id", ondelete="RESTRICT")
    )
    integrity: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    algorithm_version: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]


class AssessmentItem(UUIDPrimaryKeyMixin, Base):
    """Экземпляр задания, показанный в сессии.

    `answer_key` никогда не покидает сервер. `instance_seed` позволяет точно
    воспроизвести экземпляр при разборе спорной ситуации.
    """

    __tablename__ = "assessment_items"
    __table_args__ = (UniqueConstraint("session_id", "position"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assessment_sessions.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[int] = mapped_column(
        ForeignKey("item_families.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(SmallInteger)
    is_pilot: Mapped[bool] = mapped_column(default=False, server_default=false())
    instance_seed: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    answer_key: Mapped[dict[str, Any]] = mapped_column(JSONB)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    score: Mapped[float | None] = mapped_column(Float)
    timed_out: Mapped[bool] = mapped_column(default=False, server_default=false())
    presented_at: Mapped[datetime]
    deadline_at: Mapped[datetime]
    answered_at: Mapped[datetime | None]
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    theta_after: Mapped[float | None] = mapped_column(Float)
    se_after: Mapped[float | None] = mapped_column(Float)

    family: Mapped[ItemFamily] = relationship(lazy="raise")


class GradeHistory(UUIDPrimaryKeyMixin, Base):
    """История смен категории кандидата: на ней держится ограничение частоты смены грейда."""

    __tablename__ = "grade_history"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    from_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT")
    )
    to_category_id: Mapped[int] = mapped_column(ForeignKey("categories.id", ondelete="RESTRICT"))
    reason: Mapped[GradeChangeReason] = mapped_column(
        pg_enum(GradeChangeReason, "grade_change_reason")
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("assessment_sessions.id", ondelete="SET NULL")
    )
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
