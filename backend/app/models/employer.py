import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.models.dictionary import Industry


class CompanySize(StrEnum):
    """Размер компании по числу сотрудников."""

    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    ENTERPRISE = "enterprise"


class TrustLevel(StrEnum):
    """Уровень доверия к компании: от него зависит дневная квота приглашений."""

    NEW = "new"
    BASIC = "basic"
    VERIFIED = "verified"


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Компания-работодатель.

    Название, отрасль и описание кандидат видит в приглашении сразу. Контакты компании
    становятся способом связи, если рекрутер не указал другой.
    """

    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("inn IS NULL OR inn ~ '^[0-9]{10}([0-9]{2})?$'", name="inn_format"),
    )

    name: Mapped[str] = mapped_column(String(200))
    inn: Mapped[str | None] = mapped_column(String(12))
    website: Mapped[str | None] = mapped_column(String(200))
    industry_id: Mapped[int | None] = mapped_column(
        ForeignKey("industries.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    size: Mapped[CompanySize | None] = mapped_column(pg_enum(CompanySize, "company_size"))
    city: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(254))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    contact_telegram: Mapped[str | None] = mapped_column(String(64))
    trust_level: Mapped[TrustLevel] = mapped_column(
        pg_enum(TrustLevel, "trust_level"),
        default=TrustLevel.NEW,
        server_default=TrustLevel.NEW.value,
    )
    restricted_at: Mapped[datetime | None]
    restriction_reason: Mapped[str] = mapped_column(String(300), default="", server_default="")

    industry: Mapped[Industry | None] = relationship(lazy="raise")


class Recruiter(TimestampMixin, Base):
    """Пользователь-работодатель, действующий от имени компании.

    Связь вынесена в отдельную таблицу: у компании может быть несколько рекрутеров,
    а права на подборки, приглашения и раскрытые контакты принадлежат компании.
    """

    __tablename__ = "recruiters"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    position: Mapped[str] = mapped_column(String(120), default="", server_default="")

    company: Mapped[Company] = relationship(lazy="raise")
