"""Вакансии и отклики кандидатов

Ревизия: 0006
Предыдущая: 0005
Создана: 2026-10-07 20:12:06.975913+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

VACANCY_STATUS = postgresql.ENUM(
    "draft", "published", "closed", name="vacancy_status", create_type=False
)
APPLICATION_STATUS = postgresql.ENUM(
    "submitted",
    "viewed",
    "interview",
    "rejected",
    "withdrawn",
    name="application_status",
    create_type=False,
)
REJECT_REASON = postgresql.ENUM(
    "skills", "grade", "salary", "position_filled", "other", name="reject_reason", create_type=False
)
SKILL_IMPORTANCE = postgresql.ENUM("must", "nice", name="skill_importance", create_type=False)
ENUM_TYPES = (VACANCY_STATUS, APPLICATION_STATUS, REJECT_REASON)
NEW_NOTIFICATION_KINDS = ("application_received", "application_updated")


def upgrade() -> None:
    """Создаёт вакансии, их навыки, отклики и журнал откликов; добавляет виды уведомлений.

    Новое значение ENUM нельзя использовать в той же транзакции, где оно добавлено,
    но здесь оно только объявляется — использовать его будет приложение.
    """
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)
    for kind in NEW_NOTIFICATION_KINDS:
        op.execute(f"ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS '{kind}'")
    op.create_table(
        "vacancies",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=True),
        sa.Column("need_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("specialization_id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "grade_ids",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'::integer[]"),
            nullable=False,
        ),
        sa.Column(
            "work_formats",
            postgresql.ARRAY(sa.String(length=16)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("salary_from", sa.Integer(), nullable=False),
        sa.Column("salary_to", sa.Integer(), nullable=False),
        sa.Column("salary_gross", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "status",
            VACANCY_STATUS,
            server_default="draft",
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
            "salary_from > 0 AND salary_from <= salary_to", name=op.f("ck_vacancies_salary_range")
        ),
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["users.id"],
            name=op.f("fk_vacancies_author_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_vacancies_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["need_id"],
            ["hiring_needs.id"],
            name=op.f("fk_vacancies_need_id_hiring_needs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_vacancies_specialization_id_specializations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vacancies")),
    )
    op.create_index(op.f("ix_vacancies_company_id"), "vacancies", ["company_id"], unique=False)
    op.create_index(
        "ix_vacancies_status_published", "vacancies", ["status", "published_at"], unique=False
    )
    op.create_table(
        "applications",
        sa.Column("vacancy_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("cover_letter", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            APPLICATION_STATUS,
            server_default="submitted",
            nullable=False,
        ),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column(
            "reject_reason",
            REJECT_REASON,
            nullable=True,
        ),
        sa.Column("reject_comment", sa.String(length=500), server_default="", nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_applications_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_applications_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancies.id"],
            name=op.f("fk_applications_vacancy_id_vacancies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_applications")),
        sa.UniqueConstraint(
            "vacancy_id", "candidate_id", name=op.f("uq_applications_vacancy_id_candidate_id")
        ),
    )
    op.create_index(
        op.f("ix_applications_candidate_id"), "applications", ["candidate_id"], unique=False
    )
    op.create_index(
        op.f("ix_applications_company_id"), "applications", ["company_id"], unique=False
    )
    op.create_index(op.f("ix_applications_status"), "applications", ["status"], unique=False)
    op.create_index(
        op.f("ix_applications_vacancy_id"), "applications", ["vacancy_id"], unique=False
    )
    op.create_table(
        "vacancy_skills",
        sa.Column("vacancy_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("importance", SKILL_IMPORTANCE, nullable=False),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_vacancy_skills_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["vacancy_id"],
            ["vacancies.id"],
            name=op.f("fk_vacancy_skills_vacancy_id_vacancies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("vacancy_id", "skill_id", name=op.f("pk_vacancy_skills")),
    )
    op.create_table(
        "application_events",
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column(
            "from_status",
            APPLICATION_STATUS,
            nullable=True,
        ),
        sa.Column(
            "to_status",
            APPLICATION_STATUS,
            nullable=False,
        ),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_application_events_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_application_events_application_id_applications"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_events")),
    )
    op.create_index(
        op.f("ix_application_events_application_id"),
        "application_events",
        ["application_id"],
        unique=False,
    )


def downgrade() -> None:
    """Удаляет таблицы и типы вакансий.

    Значения в notification_kind остаются: PostgreSQL не умеет удалять значения ENUM,
    а лишние значения ничему не мешают.
    """
    op.drop_index(op.f("ix_application_events_application_id"), table_name="application_events")
    op.drop_table("application_events")
    op.drop_table("vacancy_skills")
    op.drop_index(op.f("ix_applications_vacancy_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_status"), table_name="applications")
    op.drop_index(op.f("ix_applications_company_id"), table_name="applications")
    op.drop_index(op.f("ix_applications_candidate_id"), table_name="applications")
    op.drop_table("applications")
    op.drop_index("ix_vacancies_status_published", table_name="vacancies")
    op.drop_index(op.f("ix_vacancies_company_id"), table_name="vacancies")
    op.drop_table("vacancies")
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.drop(bind, checkfirst=True)
