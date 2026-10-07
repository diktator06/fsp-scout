"""Микрозадачи от работодателей и их выдача кандидатам

Ревизия: 0007
Предыдущая: 0006
Создана: 2026-10-07 20:30:25.480138+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MICROTASK_KIND = postgresql.ENUM("solve", "approach", name="microtask_kind", create_type=False)
MICROTASK_STATUS = postgresql.ENUM(
    "active", "archived", name="microtask_status", create_type=False
)
ASSIGNMENT_STATUS = postgresql.ENUM(
    "assigned",
    "submitted",
    "graded",
    "expired",
    "skipped",
    name="microtask_assignment_status",
    create_type=False,
)
ENUM_TYPES = (MICROTASK_KIND, MICROTASK_STATUS, ASSIGNMENT_STATUS)
NEW_NOTIFICATION_KINDS = ("microtask_submitted", "microtask_graded")


def upgrade() -> None:
    """Создаёт микрозадачи и их выдачу кандидатам; добавляет виды уведомлений."""
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)
    for kind in NEW_NOTIFICATION_KINDS:
        op.execute(f"ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS '{kind}'")
    op.create_table(
        "microtasks",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("specialization_id", sa.SmallInteger(), nullable=False),
        sa.Column("kind", MICROTASK_KIND, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column(
            "options", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column(
            "answer_key",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("rubric", sa.Text(), server_default="", nullable=False),
        sa.Column("time_limit_minutes", sa.SmallInteger(), server_default="20", nullable=False),
        sa.Column(
            "status",
            MICROTASK_STATUS,
            server_default="active",
            nullable=False,
        ),
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
            "time_limit_minutes BETWEEN 5 AND 240", name=op.f("ck_microtasks_time_limit_range")
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name=op.f("fk_microtasks_author_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_microtasks_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_microtasks_specialization_id_specializations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_microtasks")),
    )
    op.create_index(op.f("ix_microtasks_company_id"), "microtasks", ["company_id"], unique=False)
    op.create_index(
        "ix_microtasks_specialization_status",
        "microtasks",
        ["specialization_id", "status"],
        unique=False,
    )
    op.create_table(
        "microtask_assignments",
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            ASSIGNMENT_STATUS,
            server_default="assigned",
            nullable=False,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answer", sa.Text(), server_default="", nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("feedback", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("graded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graded_by", sa.Uuid(), nullable=True),
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
            "rating IS NULL OR rating BETWEEN 1 AND 5",
            name=op.f("ck_microtask_assignments_rating_range"),
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 1)",
            name=op.f("ck_microtask_assignments_score_range"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_microtask_assignments_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["graded_by"],
            ["users.id"],
            name=op.f("fk_microtask_assignments_graded_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["microtasks.id"],
            name=op.f("fk_microtask_assignments_task_id_microtasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_microtask_assignments")),
        sa.UniqueConstraint(
            "task_id", "candidate_id", name=op.f("uq_microtask_assignments_task_id_candidate_id")
        ),
    )
    op.create_index(
        "ix_microtask_assignments_candidate_status",
        "microtask_assignments",
        ["candidate_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_microtask_assignments_task_id"), "microtask_assignments", ["task_id"], unique=False
    )


def downgrade() -> None:
    """Удаляет микрозадачи. Значения notification_kind остаются: PostgreSQL их не удаляет."""
    op.drop_index(op.f("ix_microtask_assignments_task_id"), table_name="microtask_assignments")
    op.drop_index("ix_microtask_assignments_candidate_status", table_name="microtask_assignments")
    op.drop_table("microtask_assignments")
    op.drop_index("ix_microtasks_specialization_status", table_name="microtasks")
    op.drop_index(op.f("ix_microtasks_company_id"), table_name="microtasks")
    op.drop_table("microtasks")
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.drop(bind, checkfirst=True)
