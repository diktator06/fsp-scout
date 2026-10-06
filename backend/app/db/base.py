import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """Текущее время в UTC с часовым поясом: в базе все отметки времени `timestamptz`."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Базовый класс ORM-моделей.

    Единая naming convention даёт предсказуемые имена ограничений, и Alembic генерирует
    одинаковые миграции на любой машине. `eager_defaults` забирает серверные значения
    (`created_at`) через RETURNING сразу при INSERT: в асинхронной сессии иначе
    обращение к такому полю закончилось бы неявной ленивой загрузкой.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: DateTime(timezone=True)}
    __mapper_args__ = {"eager_defaults": True}


class UUIDPrimaryKeyMixin:
    """Первичный ключ UUID: идентификаторы не перебираются и безопасно светятся в URL."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class CreatedAtMixin:
    """Отметка создания записи."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class TimestampMixin(CreatedAtMixin):
    """Отметки создания и последнего изменения записи."""

    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), default=utc_now, onupdate=utc_now
    )
