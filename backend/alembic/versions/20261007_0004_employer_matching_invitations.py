"""Компании, потребности и подборки, приглашения, раскрытие контактов, уведомления

Ревизия: 0004
Предыдущая: 0003
Создана: 2026-10-07 02:12:56.508118+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COMPANY_SIZE = postgresql.ENUM(
    "tiny", "small", "medium", "large", "enterprise", name="company_size", create_type=False
)
TRUST_LEVEL = postgresql.ENUM("new", "basic", "verified", name="trust_level", create_type=False)
NOTIFICATION_KIND = postgresql.ENUM(
    "invitation_received",
    "invitation_accepted",
    "invitation_declined",
    "invitation_withdrawn",
    "invitation_expired",
    name="notification_kind",
    create_type=False,
)
NEED_STATUS = postgresql.ENUM("active", "closed", name="need_status", create_type=False)
DISCLOSURE_REASON = postgresql.ENUM(
    "invitation_accepted", "application", name="disclosure_reason", create_type=False
)
WORK_FORMAT = postgresql.ENUM("office", "hybrid", "remote", name="work_format", create_type=False)
INVITATION_STATUS = postgresql.ENUM(
    "sent",
    "viewed",
    "accepted",
    "declined",
    "withdrawn",
    "expired",
    name="invitation_status",
    create_type=False,
)
DECLINE_REASON = postgresql.ENUM(
    "salary",
    "stack",
    "work_format",
    "not_looking",
    "company",
    "other",
    name="decline_reason",
    create_type=False,
)
SKILL_IMPORTANCE = postgresql.ENUM("must", "nice", name="skill_importance", create_type=False)
SHORTLIST_MARK = postgresql.ENUM("pinned", "hidden", name="shortlist_mark", create_type=False)
ENUM_TYPES = (
    COMPANY_SIZE,
    TRUST_LEVEL,
    NOTIFICATION_KIND,
    NEED_STATUS,
    DISCLOSURE_REASON,
    WORK_FORMAT,
    INVITATION_STATUS,
    DECLINE_REASON,
    SKILL_IMPORTANCE,
    SHORTLIST_MARK,
)


def upgrade() -> None:
    """Создаёт таблицы шага 3.

    Типы ENUM создаются заранее и один раз: `invitation_status` используется в двух
    таблицах, и повторный `CREATE TYPE` внутри второго `create_table` упал бы.
    """
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)
    op.create_table(
        "audit_log",
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column(
            "meta", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
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
            name=op.f("fk_audit_log_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_table(
        "companies",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=True),
        sa.Column("website", sa.String(length=200), nullable=True),
        sa.Column("industry_id", sa.SmallInteger(), nullable=True),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "size",
            COMPANY_SIZE,
            nullable=True,
        ),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("contact_email", sa.String(length=254), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("contact_telegram", sa.String(length=64), nullable=True),
        sa.Column(
            "trust_level",
            TRUST_LEVEL,
            server_default="new",
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
            "inn IS NULL OR inn ~ '^[0-9]{10}([0-9]{2})?$'", name=op.f("ck_companies_inn_format")
        ),
        sa.ForeignKeyConstraint(
            ["industry_id"],
            ["industries.id"],
            name=op.f("fk_companies_industry_id_industries"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    op.create_table(
        "notifications",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            NOTIFICATION_KIND,
            nullable=False,
        ),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_notifications_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
    )
    op.create_index(
        "ix_notifications_user_unread", "notifications", ["user_id", "read_at"], unique=False
    )
    op.create_table(
        "skill_relations",
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("related_skill_id", sa.Integer(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "similarity > 0 AND similarity <= 1", name=op.f("ck_skill_relations_similarity_range")
        ),
        sa.CheckConstraint(
            "skill_id <> related_skill_id", name=op.f("ck_skill_relations_not_self")
        ),
        sa.ForeignKeyConstraint(
            ["related_skill_id"],
            ["skills.id"],
            name=op.f("fk_skill_relations_related_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_skill_relations_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("skill_id", "related_skill_id", name=op.f("pk_skill_relations")),
    )
    op.create_table(
        "hiring_needs",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("raw_text", sa.Text(), server_default="", nullable=False),
        sa.Column("team_description", sa.Text(), server_default="", nullable=False),
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
            NEED_STATUS,
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "extraction",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
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
            "salary_from > 0 AND salary_from <= salary_to",
            name=op.f("ck_hiring_needs_salary_range"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_hiring_needs_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_hiring_needs_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_hiring_needs_specialization_id_specializations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hiring_needs")),
    )
    op.create_index(
        op.f("ix_hiring_needs_company_id"), "hiring_needs", ["company_id"], unique=False
    )
    op.create_table(
        "recruiters",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.String(length=120), server_default="", nullable=False),
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
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_recruiters_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_recruiters_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_recruiters")),
    )
    op.create_index(op.f("ix_recruiters_company_id"), "recruiters", ["company_id"], unique=False)
    op.create_table(
        "contact_disclosures",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "reason",
            DISCLOSURE_REASON,
            nullable=False,
        ),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column(
            "disclosed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_contact_disclosures_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_contact_disclosures_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contact_disclosures")),
    )
    op.create_index(
        op.f("ix_contact_disclosures_candidate_id"),
        "contact_disclosures",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        "uq_contact_disclosures_pair",
        "contact_disclosures",
        ["company_id", "candidate_id"],
        unique=True,
    )
    op.create_table(
        "invitations",
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("sender_user_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("need_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("offer_description", sa.Text(), nullable=False),
        sa.Column("salary_from", sa.Integer(), nullable=False),
        sa.Column("salary_to", sa.Integer(), nullable=False),
        sa.Column("salary_gross", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("work_format", WORK_FORMAT, nullable=False),
        sa.Column("contact_method", sa.String(length=300), nullable=False),
        sa.Column(
            "status",
            INVITATION_STATUS,
            server_default="sent",
            nullable=False,
        ),
        sa.Column(
            "decline_reason",
            DECLINE_REASON,
            nullable=True,
        ),
        sa.Column("decline_comment", sa.String(length=500), server_default="", nullable=False),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
            "salary_from > 0 AND salary_from <= salary_to", name=op.f("ck_invitations_salary_range")
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_invitations_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_invitations_company_id_companies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["need_id"],
            ["hiring_needs.id"],
            name=op.f("fk_invitations_need_id_hiring_needs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["sender_user_id"],
            ["users.id"],
            name=op.f("fk_invitations_sender_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
    )
    op.create_index(
        op.f("ix_invitations_candidate_id"), "invitations", ["candidate_id"], unique=False
    )
    op.create_index(op.f("ix_invitations_company_id"), "invitations", ["company_id"], unique=False)
    op.create_index(op.f("ix_invitations_expires_at"), "invitations", ["expires_at"], unique=False)
    op.create_index(op.f("ix_invitations_status"), "invitations", ["status"], unique=False)
    op.create_index(
        "uq_invitations_active_pair",
        "invitations",
        ["company_id", "candidate_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('sent', 'viewed')"),
    )
    op.create_table(
        "need_skills",
        sa.Column("need_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("importance", SKILL_IMPORTANCE, nullable=False),
        sa.ForeignKeyConstraint(
            ["need_id"],
            ["hiring_needs.id"],
            name=op.f("fk_need_skills_need_id_hiring_needs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_need_skills_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("need_id", "skill_id", name=op.f("pk_need_skills")),
    )
    op.create_table(
        "shortlist_marks",
        sa.Column("need_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("mark", SHORTLIST_MARK, nullable=False),
        sa.Column("note", sa.String(length=500), server_default="", nullable=False),
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
            name=op.f("fk_shortlist_marks_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["need_id"],
            ["hiring_needs.id"],
            name=op.f("fk_shortlist_marks_need_id_hiring_needs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("need_id", "candidate_id", name=op.f("pk_shortlist_marks")),
    )
    op.create_table(
        "shortlists",
        sa.Column("need_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column(
            "filters", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "stats", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("algorithm_version", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_shortlists_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["need_id"],
            ["hiring_needs.id"],
            name=op.f("fk_shortlists_need_id_hiring_needs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shortlists")),
        sa.UniqueConstraint("need_id", "version", name=op.f("uq_shortlists_need_id_version")),
    )
    op.create_index(op.f("ix_shortlists_need_id"), "shortlists", ["need_id"], unique=False)
    op.create_table(
        "invitation_events",
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "from_status",
            INVITATION_STATUS,
            nullable=True,
        ),
        sa.Column(
            "to_status",
            INVITATION_STATUS,
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
            name=op.f("fk_invitation_events_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"],
            ["invitations.id"],
            name=op.f("fk_invitation_events_invitation_id_invitations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitation_events")),
    )
    op.create_index(
        op.f("ix_invitation_events_invitation_id"),
        "invitation_events",
        ["invitation_id"],
        unique=False,
    )
    op.create_table(
        "shortlist_entries",
        sa.Column("shortlist_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("rank", sa.SmallInteger(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("breakdown", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("outside_filters", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_shortlist_entries_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shortlist_id"],
            ["shortlists.id"],
            name=op.f("fk_shortlist_entries_shortlist_id_shortlists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("shortlist_id", "candidate_id", name=op.f("pk_shortlist_entries")),
    )
    op.create_index(
        op.f("ix_shortlist_entries_candidate_id"),
        "shortlist_entries",
        ["candidate_id"],
        unique=False,
    )


def downgrade() -> None:
    """Удаляет таблицы шага 3 и их типы ENUM."""
    op.drop_index(op.f("ix_shortlist_entries_candidate_id"), table_name="shortlist_entries")
    op.drop_table("shortlist_entries")
    op.drop_index(op.f("ix_invitation_events_invitation_id"), table_name="invitation_events")
    op.drop_table("invitation_events")
    op.drop_index(op.f("ix_shortlists_need_id"), table_name="shortlists")
    op.drop_table("shortlists")
    op.drop_table("shortlist_marks")
    op.drop_table("need_skills")
    op.drop_index(
        "uq_invitations_active_pair",
        table_name="invitations",
        postgresql_where=sa.text("status IN ('sent', 'viewed')"),
    )
    op.drop_index(op.f("ix_invitations_status"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_expires_at"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_company_id"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_candidate_id"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_index("uq_contact_disclosures_pair", table_name="contact_disclosures")
    op.drop_index(op.f("ix_contact_disclosures_candidate_id"), table_name="contact_disclosures")
    op.drop_table("contact_disclosures")
    op.drop_index(op.f("ix_recruiters_company_id"), table_name="recruiters")
    op.drop_table("recruiters")
    op.drop_index(op.f("ix_hiring_needs_company_id"), table_name="hiring_needs")
    op.drop_table("hiring_needs")
    op.drop_table("skill_relations")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("companies")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_table("audit_log")
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.drop(bind, checkfirst=True)
