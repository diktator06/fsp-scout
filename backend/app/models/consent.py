import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin
from app.db.types import pg_enum


class ConsentType(StrEnum):
    """Виды согласий по 152-ФЗ. Каждое даётся и отзывается отдельно."""

    PERSONAL_DATA_PROCESSING = "personal_data_processing"
    BANK_PUBLICATION = "bank_publication"
    FSP_DATA_ACCESS = "fsp_data_access"


class Consent(UUIDPrimaryKeyMixin, Base):
    """Журнал согласий (только добавление записей).

    Отзыв не удаляет строку, а проставляет `revoked_at`. Так сохраняется история,
    которую оператор ПДн обязан предъявить по запросу.
    """

    __tablename__ = "consents"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    consent_type: Mapped[ConsentType] = mapped_column(pg_enum(ConsentType, "consent_type"))
    document_version: Mapped[str] = mapped_column(String(32))
    granted_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revoked_at: Mapped[datetime | None]
    ip_address: Mapped[str | None] = mapped_column(String(45))
