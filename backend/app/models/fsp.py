import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum


class FspEventLevel(StrEnum):
    """Уровень соревнования. Показывается как справка и на балл не влияет (просьба менторов)."""

    INTERNATIONAL = "international"
    NATIONAL = "national"
    INTERREGIONAL = "interregional"
    REGIONAL = "regional"
    LOCAL = "local"


class FspParticipationFormat(StrEnum):
    """Личное или командное участие."""

    INDIVIDUAL = "individual"
    TEAM = "team"


class FspResultStatus(StrEnum):
    """Результат участия по протоколу соревнования."""

    WINNER = "winner"
    PRIZE = "prize"
    FINALIST = "finalist"
    PARTICIPANT = "participant"


class FspSyncStatus(StrEnum):
    """Итог синхронизации с реестром ФСП."""

    OK = "ok"
    EMPTY = "empty"
    ERROR = "error"


class FspState(StrEnum):
    """Что известно о ФСП кандидата. Хранится не в базе, а выводится из привязки и приватности.

    Каждое состояние штатное: отсутствие привязки или истории не штрафуется.
    """

    NOT_LINKED = "not_linked"
    LINKED_EMPTY = "linked_empty"
    LINKED = "linked"
    HIDDEN = "hidden"


class OidcFlowPurpose(StrEnum):
    """Зачем начат вход через ФСП ID: привязать профиль или войти в аккаунт."""

    LINK = "link"
    LOGIN = "login"


class FspLink(CreatedAtMixin, Base):
    """Привязка профиля кандидата к участнику ФСП.

    Один участник ФСП привязывается только к одному профилю: иначе чужие победы
    можно было бы приписать себе. Отвязка удаляет строку вместе с достижениями.
    """

    __tablename__ = "fsp_links"

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), primary_key=True
    )
    participant_id: Mapped[str] = mapped_column(String(64), unique=True)
    linked_at: Mapped[datetime] = mapped_column(server_default=func.now())
    synced_at: Mapped[datetime | None]
    region: Mapped[str | None] = mapped_column(String(120))
    sport_rank: Mapped[str | None] = mapped_column(String(64))


class FspAchievement(UUIDPrimaryKeyMixin, Base):
    """Участие кандидата в соревновании ФСП — копия записи реестра на момент синхронизации."""

    __tablename__ = "fsp_achievements"
    __table_args__ = (
        UniqueConstraint("candidate_id", "external_event_id"),
        CheckConstraint("place IS NULL OR place > 0", name="place_positive"),
        CheckConstraint(
            "participants_total IS NULL OR participants_total > 0", name="participants_positive"
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"), index=True
    )
    external_event_id: Mapped[str] = mapped_column(String(64))
    event_name: Mapped[str] = mapped_column(String(300))
    event_level: Mapped[FspEventLevel] = mapped_column(pg_enum(FspEventLevel, "fsp_event_level"))
    discipline: Mapped[str] = mapped_column(String(160))
    event_date: Mapped[date] = mapped_column(Date)
    participation_format: Mapped[FspParticipationFormat] = mapped_column(
        pg_enum(FspParticipationFormat, "fsp_participation_format")
    )
    team_name: Mapped[str | None] = mapped_column(String(200))
    team_role: Mapped[str | None] = mapped_column(String(64))
    place: Mapped[int | None] = mapped_column(SmallInteger)
    participants_total: Mapped[int | None] = mapped_column(Integer)
    result_status: Mapped[FspResultStatus] = mapped_column(
        pg_enum(FspResultStatus, "fsp_result_status")
    )
    is_online: Mapped[bool] = mapped_column(default=False, server_default=false())
    rating_points: Mapped[float | None] = mapped_column(Float)
    protocol_url: Mapped[str | None] = mapped_column(String(500))
    synced_at: Mapped[datetime] = mapped_column(server_default=func.now())


class FspSyncLog(UUIDPrimaryKeyMixin, Base):
    """Журнал синхронизаций с реестром: по нему видно, свежие ли данные и почему нет."""

    __tablename__ = "fsp_sync_log"
    __table_args__ = (Index("ix_fsp_sync_log_candidate_time", "candidate_id", "synced_at"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_profiles.id", ondelete="CASCADE")
    )
    status: Mapped[FspSyncStatus] = mapped_column(pg_enum(FspSyncStatus, "fsp_sync_status"))
    achievements_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    synced_at: Mapped[datetime] = mapped_column(server_default=func.now())


class OidcFlowState(CreatedAtMixin, Base):
    """Незавершённый вход через ФСП ID: state, PKCE-верификатор и nonce.

    Запись одноразовая и живёт несколько минут. `state` защищает от подмены ответа
    (CSRF), верификатор PKCE — от перехвата кода, nonce — от повтора id_token.
    """

    __tablename__ = "oidc_flow_states"

    state: Mapped[str] = mapped_column(String(128), primary_key=True)
    purpose: Mapped[OidcFlowPurpose] = mapped_column(pg_enum(OidcFlowPurpose, "oidc_flow_purpose"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    code_verifier: Mapped[str] = mapped_column(String(128))
    nonce: Mapped[str] = mapped_column(String(128))
    redirect_uri: Mapped[str] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(index=True)
