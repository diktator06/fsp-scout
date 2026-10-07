"""Интеграция с ФСП: привязка ФСП ID, достижения, журнал синхронизации, состояния OIDC

Ревизия: 0005
Предыдущая: 0004
Создана: 2026-10-07 09:28:39.672028+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OIDC_FLOW_PURPOSE = postgresql.ENUM("link", "login", name="oidc_flow_purpose", create_type=False)
FSP_EVENT_LEVEL = postgresql.ENUM(
    "international",
    "national",
    "interregional",
    "regional",
    "local",
    name="fsp_event_level",
    create_type=False,
)
FSP_PARTICIPATION_FORMAT = postgresql.ENUM(
    "individual", "team", name="fsp_participation_format", create_type=False
)
FSP_RESULT_STATUS = postgresql.ENUM(
    "winner", "prize", "finalist", "participant", name="fsp_result_status", create_type=False
)
FSP_SYNC_STATUS = postgresql.ENUM("ok", "empty", "error", name="fsp_sync_status", create_type=False)
ENUM_TYPES = (
    OIDC_FLOW_PURPOSE,
    FSP_EVENT_LEVEL,
    FSP_PARTICIPATION_FORMAT,
    FSP_RESULT_STATUS,
    FSP_SYNC_STATUS,
)


def upgrade() -> None:
    """Создаёт таблицы шага 4: привязку к ФСП ID, копию достижений и служебные журналы."""
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)
    op.create_table(
        "oidc_flow_states",
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("purpose", OIDC_FLOW_PURPOSE, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oidc_flow_states_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("state", name=op.f("pk_oidc_flow_states")),
    )
    op.create_index(
        op.f("ix_oidc_flow_states_expires_at"), "oidc_flow_states", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_oidc_flow_states_user_id"), "oidc_flow_states", ["user_id"], unique=False
    )
    op.create_table(
        "fsp_achievements",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("external_event_id", sa.String(length=64), nullable=False),
        sa.Column("event_name", sa.String(length=300), nullable=False),
        sa.Column(
            "event_level",
            FSP_EVENT_LEVEL,
            nullable=False,
        ),
        sa.Column("discipline", sa.String(length=160), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column(
            "participation_format",
            FSP_PARTICIPATION_FORMAT,
            nullable=False,
        ),
        sa.Column("team_name", sa.String(length=200), nullable=True),
        sa.Column("team_role", sa.String(length=64), nullable=True),
        sa.Column("place", sa.SmallInteger(), nullable=True),
        sa.Column("participants_total", sa.Integer(), nullable=True),
        sa.Column(
            "result_status",
            FSP_RESULT_STATUS,
            nullable=False,
        ),
        sa.Column("is_online", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rating_points", sa.Float(), nullable=True),
        sa.Column("protocol_url", sa.String(length=500), nullable=True),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "participants_total IS NULL OR participants_total > 0",
            name=op.f("ck_fsp_achievements_participants_positive"),
        ),
        sa.CheckConstraint(
            "place IS NULL OR place > 0", name=op.f("ck_fsp_achievements_place_positive")
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_fsp_achievements_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fsp_achievements")),
        sa.UniqueConstraint(
            "candidate_id",
            "external_event_id",
            name=op.f("uq_fsp_achievements_candidate_id_external_event_id"),
        ),
    )
    op.create_index(
        op.f("ix_fsp_achievements_candidate_id"), "fsp_achievements", ["candidate_id"], unique=False
    )
    op.create_table(
        "fsp_links",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("participant_id", sa.String(length=64), nullable=False),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("sport_rank", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_fsp_links_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", name=op.f("pk_fsp_links")),
        sa.UniqueConstraint("participant_id", name=op.f("uq_fsp_links_participant_id")),
    )
    op.create_table(
        "fsp_sync_log",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("status", FSP_SYNC_STATUS, nullable=False),
        sa.Column("achievements_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "synced_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_fsp_sync_log_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fsp_sync_log")),
    )
    op.create_index(
        "ix_fsp_sync_log_candidate_time",
        "fsp_sync_log",
        ["candidate_id", "synced_at"],
        unique=False,
    )


def downgrade() -> None:
    """Удаляет таблицы и типы шага 4."""
    op.drop_index("ix_fsp_sync_log_candidate_time", table_name="fsp_sync_log")
    op.drop_table("fsp_sync_log")
    op.drop_table("fsp_links")
    op.drop_index(op.f("ix_fsp_achievements_candidate_id"), table_name="fsp_achievements")
    op.drop_table("fsp_achievements")
    op.drop_index(op.f("ix_oidc_flow_states_user_id"), table_name="oidc_flow_states")
    op.drop_index(op.f("ix_oidc_flow_states_expires_at"), table_name="oidc_flow_states")
    op.drop_table("oidc_flow_states")
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.drop(bind, checkfirst=True)
