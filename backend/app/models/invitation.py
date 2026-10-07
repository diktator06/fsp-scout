import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, func, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum
from app.models.candidate import WorkFormat


class InvitationStatus(StrEnum):
    """Статусы приглашения. Переходы задаёт автомат в `services/invitations/state_machine.py`."""

    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


ACTIVE_INVITATION_STATUSES = (InvitationStatus.SENT, InvitationStatus.VIEWED)


class DeclineReason(StrEnum):
    """Причина отказа: агрегаты по ним работодатель видит как обратную связь."""

    SALARY = "salary"
    STACK = "stack"
    WORK_FORMAT = "work_format"
    NOT_LOOKING = "not_looking"
    COMPANY = "company"
    OTHER = "other"


class DisclosureReason(StrEnum):
    """Основание раскрытия контактов: принятое приглашение или собственный отклик кандидата."""

    INVITATION_ACCEPTED = "invitation_accepted"
    APPLICATION = "application"


class Invitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Приглашение работодателя конкретному кандидату.

    Вилка «от–до» обязательна (ограничение в базе дублирует проверку сервиса), как и
    описание предложения и способ связи. Одновременно у пары «компания — кандидат»
    может быть только одно активное приглашение: за этим следит частичный уникальный
    индекс, а не только код.
    """

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("salary_from > 0 AND salary_from <= salary_to", name="salary_range"),
        Index(
            "uq_invitations_active_pair",
            "company_id",
            "candidate_id",
            unique=True,
            postgresql_where=text("status IN ('sent', 'viewed')"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    need_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("hiring_needs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(200))
    offer_description: Mapped[str] = mapped_column(Text)
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    salary_gross: Mapped[bool] = mapped_column(default=True, server_default=true())
    work_format: Mapped[WorkFormat] = mapped_column(pg_enum(WorkFormat, "work_format"))
    contact_method: Mapped[str] = mapped_column(String(300))
    status: Mapped[InvitationStatus] = mapped_column(
        pg_enum(InvitationStatus, "invitation_status"),
        default=InvitationStatus.SENT,
        server_default=InvitationStatus.SENT.value,
        index=True,
    )
    decline_reason: Mapped[DeclineReason | None] = mapped_column(
        pg_enum(DeclineReason, "decline_reason")
    )
    decline_comment: Mapped[str] = mapped_column(String(500), default="", server_default="")
    viewed_at: Mapped[datetime | None]
    responded_at: Mapped[datetime | None]
    expires_at: Mapped[datetime] = mapped_column(index=True)


class InvitationEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Журнал переходов приглашения: из него строится таймлайн у обеих сторон."""

    __tablename__ = "invitation_events"

    invitation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invitations.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[InvitationStatus | None] = mapped_column(
        pg_enum(InvitationStatus, "invitation_status")
    )
    to_status: Mapped[InvitationStatus] = mapped_column(
        pg_enum(InvitationStatus, "invitation_status")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class ContactDisclosure(UUIDPrimaryKeyMixin, Base):
    """Право компании видеть контакты кандидата.

    Единственный источник этого права: пока записи нет, контакты не попадают ни в
    один ответ API. Запись появляется, когда кандидат принимает приглашение или
    сам откликается на вакансию.
    """

    __tablename__ = "contact_disclosures"
    __table_args__ = (
        Index("uq_contact_disclosures_pair", "company_id", "candidate_id", unique=True),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[DisclosureReason] = mapped_column(pg_enum(DisclosureReason, "disclosure_reason"))
    source_id: Mapped[uuid.UUID | None]
    disclosed_at: Mapped[datetime] = mapped_column(server_default=func.now())
