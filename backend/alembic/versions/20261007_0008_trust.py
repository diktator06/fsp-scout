"""Жалобы кандидатов и ограничение компаний на время проверки

Ревизия: 0008
Предыдущая: 0007
Создана: 2026-10-07 20:49:49.723510+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPLAINT_TARGET = postgresql.ENUM(
    "invitation", "vacancy", "company", name="complaint_target", create_type=False
)
COMPLAINT_REASON = postgresql.ENUM(
    "fake_offer",
    "salary_mismatch",
    "payment_request",
    "spam",
    "rude",
    "other",
    name="complaint_reason",
    create_type=False,
)
COMPLAINT_STATUS = postgresql.ENUM(
    "open", "confirmed", "rejected", name="complaint_status", create_type=False
)
ENUM_TYPES = (COMPLAINT_TARGET, COMPLAINT_REASON, COMPLAINT_STATUS)


def upgrade() -> None:
    """Создаёт жалобы, добавляет компании отметку об ограничении и вид уведомления."""
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)
    op.execute("ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'company_restricted'")
    op.create_table(
        "complaints",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "target_type",
            COMPLAINT_TARGET,
            nullable=False,
        ),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column(
            "reason",
            COMPLAINT_REASON,
            nullable=False,
        ),
        sa.Column("comment", sa.String(length=1000), server_default="", nullable=False),
        sa.Column(
            "status",
            COMPLAINT_STATUS,
            server_default="open",
            nullable=False,
        ),
        sa.Column("resolution_note", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name=op.f("fk_complaints_author_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_complaints_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by"],
            ["users.id"],
            name=op.f("fk_complaints_resolved_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complaints")),
        sa.UniqueConstraint(
            "author_user_id",
            "target_type",
            "target_id",
            name=op.f("uq_complaints_author_user_id_target_type_target_id"),
        ),
    )
    op.create_index(
        "ix_complaints_company_status", "complaints", ["company_id", "status"], unique=False
    )
    op.add_column(
        "companies", sa.Column("restricted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "companies",
        sa.Column("restriction_reason", sa.String(length=300), server_default="", nullable=False),
    )


def downgrade() -> None:
    """Удаляет жалобы и отметку об ограничении. Значение notification_kind остаётся."""
    op.drop_column("companies", "restriction_reason")
    op.drop_column("companies", "restricted_at")
    op.drop_index("ix_complaints_company_status", table_name="complaints")
    op.drop_table("complaints")
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.drop(bind, checkfirst=True)
