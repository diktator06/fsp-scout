"""Начальная схема: пользователи, сессии, согласия, справочники

Ревизия: 0001
Предыдущая:
Создана: 2026-10-06 16:25:55.593628+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENUM_TYPES = ("session_revoke_reason", "consent_type", "auth_provider", "user_role", "skill_kind")


def upgrade() -> None:
    """Создаёт таблицы идентификации, согласий и справочников.

    Расширение `vector` (pgvector) подключается здесь же: колонка эмбеддингов навыков
    создаётся в этой миграции, а позже на нём построен семантический подбор.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "grades",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("experience_hint", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("default_theta_cut", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grades")),
        sa.UniqueConstraint("code", name=op.f("uq_grades_code")),
        sa.UniqueConstraint("rank", name=op.f("uq_grades_rank")),
    )
    op.create_table(
        "industries",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_industries")),
        sa.UniqueConstraint("code", name=op.f("uq_industries_code")),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "language", "framework", "database", "tool", "concept", "soft", name="skill_kind"
            ),
            nullable=False,
        ),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.String(length=128)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
        sa.UniqueConstraint("slug", name=op.f("uq_skills_slug")),
    )
    op.create_table(
        "specializations",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_specializations")),
        sa.UniqueConstraint("code", name=op.f("uq_specializations_code")),
    )
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "role", sa.Enum("candidate", "employer", "methodist", name="user_role"), nullable=False
        ),
        sa.Column(
            "is_email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "auth_provider",
            sa.Enum("local", "oidc", name="auth_provider"),
            server_default="local",
            nullable=False,
        ),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "auth_provider <> 'local' OR password_hash IS NOT NULL",
            name=op.f("ck_users_local_account_has_password"),
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("external_subject", name=op.f("uq_users_external_subject")),
    )
    op.create_table(
        "categories",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("specialization_id", sa.SmallInteger(), nullable=False),
        sa.Column("grade_id", sa.SmallInteger(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("theta_cut", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["grade_id"],
            ["grades.id"],
            name=op.f("fk_categories_grade_id_grades"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_categories_specialization_id_specializations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("code", name=op.f("uq_categories_code")),
        sa.UniqueConstraint(
            "specialization_id", "grade_id", name=op.f("uq_categories_specialization_id_grade_id")
        ),
    )
    op.create_index(
        op.f("ix_categories_specialization_id"), "categories", ["specialization_id"], unique=False
    )
    op.create_table(
        "consents",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "consent_type",
            sa.Enum(
                "personal_data_processing",
                "bank_publication",
                "fsp_data_access",
                name="consent_type",
            ),
            nullable=False,
        ),
        sa.Column("document_version", sa.String(length=32), nullable=False),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_consents_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consents")),
    )
    op.create_index(op.f("ix_consents_user_id"), "consents", ["user_id"], unique=False)
    op.create_table(
        "email_verification_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_email_verification_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_verification_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_email_verification_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_email_verification_tokens_user_id"),
        "email_verification_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "refresh_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoke_reason",
            sa.Enum("rotated", "logout", "reuse_detected", "expired", name="session_revoke_reason"),
            nullable=True,
        ),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_sessions.id"],
            name=op.f("fk_refresh_sessions_replaced_by_id_refresh_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_sessions_token_hash")),
    )
    op.create_index(
        op.f("ix_refresh_sessions_family_id"), "refresh_sessions", ["family_id"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_sessions_user_id"), "refresh_sessions", ["user_id"], unique=False
    )
    op.create_table(
        "specialization_skills",
        sa.Column("specialization_id", sa.SmallInteger(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("typical_weight", sa.Float(), server_default="0.5", nullable=False),
        sa.CheckConstraint(
            "typical_weight >= 0 AND typical_weight <= 1",
            name=op.f("ck_specialization_skills_weight_range"),
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_specialization_skills_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_specialization_skills_specialization_id_specializations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "specialization_id", "skill_id", name=op.f("pk_specialization_skills")
        ),
    )
    op.create_index(
        op.f("ix_specialization_skills_skill_id"),
        "specialization_skills",
        ["skill_id"],
        unique=False,
    )


def downgrade() -> None:
    """Удаляет таблицы и типы ENUM начальной схемы.

    Autogenerate не удаляет типы ENUM вместе с таблицами, поэтому делаем это явно,
    иначе повторный `upgrade` упадёт на «type already exists».
    """
    op.drop_index(op.f("ix_specialization_skills_skill_id"), table_name="specialization_skills")
    op.drop_table("specialization_skills")
    op.drop_index(op.f("ix_refresh_sessions_user_id"), table_name="refresh_sessions")
    op.drop_index(op.f("ix_refresh_sessions_family_id"), table_name="refresh_sessions")
    op.drop_table("refresh_sessions")
    op.drop_index(
        op.f("ix_email_verification_tokens_user_id"), table_name="email_verification_tokens"
    )
    op.drop_table("email_verification_tokens")
    op.drop_index(op.f("ix_consents_user_id"), table_name="consents")
    op.drop_table("consents")
    op.drop_index(op.f("ix_categories_specialization_id"), table_name="categories")
    op.drop_table("categories")
    op.drop_table("users")
    op.drop_table("specializations")
    op.drop_table("skills")
    op.drop_table("industries")
    op.drop_table("grades")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
