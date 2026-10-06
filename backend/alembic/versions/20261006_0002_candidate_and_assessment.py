"""Профиль кандидата и механика тестирования

Ревизия: 0002
Предыдущая: 0001
Создана: 2026-10-06 17:20:13.932113+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENUM_TYPES = (
    "grade_change_reason",
    "session_outcome",
    "session_status",
    "item_origin",
    "item_family_status",
    "response_format",
    "skill_source",
    "search_status",
)


def upgrade() -> None:
    """Создаёт таблицы профиля кандидата, банка заданий, опросов и сессий тестирования."""
    op.create_table(
        "competencies",
        sa.Column("id", sa.SmallInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "gate_skill_slugs",
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "verifies_skill_slugs",
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_competencies")),
        sa.UniqueConstraint("code", name=op.f("uq_competencies_code")),
    )
    op.create_table(
        "item_families",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("competency_id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "response_format",
            sa.Enum("single_choice", "numeric", name="response_format"),
            nullable=False,
        ),
        sa.Column("nominal_grade_id", sa.SmallInteger(), nullable=False),
        sa.Column("irt_a", sa.Float(), nullable=False),
        sa.Column("irt_b", sa.Float(), nullable=False),
        sa.Column("irt_c", sa.Float(), server_default="0", nullable=False),
        sa.Column("time_limit_sec", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft", "pilot", "active", "compromised", "retired", name="item_family_status"
            ),
            nullable=False,
        ),
        sa.Column(
            "origin",
            sa.Enum("expert", "llm_assisted", name="item_origin"),
            server_default="expert",
            nullable=False,
        ),
        sa.Column("exposure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("responses_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("correct_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("version", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("calibrated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("irt_a > 0", name=op.f("ck_item_families_discrimination_positive")),
        sa.CheckConstraint(
            "irt_c >= 0 AND irt_c < 1", name=op.f("ck_item_families_guessing_range")
        ),
        sa.CheckConstraint(
            "time_limit_sec BETWEEN 15 AND 900", name=op.f("ck_item_families_time_limit_range")
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name=op.f("fk_item_families_competency_id_competencies"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["nominal_grade_id"],
            ["grades.id"],
            name=op.f("fk_item_families_nominal_grade_id_grades"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_families")),
        sa.UniqueConstraint("code", name=op.f("uq_item_families_code")),
    )
    op.create_index(
        op.f("ix_item_families_competency_id"), "item_families", ["competency_id"], unique=False
    )
    op.create_table(
        "specialization_competencies",
        sa.Column("specialization_id", sa.SmallInteger(), nullable=False),
        sa.Column("competency_id", sa.SmallInteger(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.CheckConstraint(
            "weight > 0 AND weight <= 1", name=op.f("ck_specialization_competencies_weight_range")
        ),
        sa.ForeignKeyConstraint(
            ["competency_id"],
            ["competencies.id"],
            name=op.f("fk_specialization_competencies_competency_id_competencies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_specialization_competencies_specialization_id_specializations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "specialization_id", "competency_id", name=op.f("pk_specialization_competencies")
        ),
    )
    op.create_table(
        "candidate_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("public_alias", sa.String(length=8), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("telegram", sa.String(length=64), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("about", sa.Text(), server_default="", nullable=False),
        sa.Column("experience_years", sa.Float(), nullable=True),
        sa.Column(
            "team_roles",
            postgresql.ARRAY(sa.String(length=32)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "soft_skills",
            postgresql.ARRAY(sa.String(length=64)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "work_formats",
            postgresql.ARRAY(sa.String(length=16)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "relocation_ready", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("salary_expectation_from", sa.Integer(), nullable=True),
        sa.Column(
            "search_status",
            sa.Enum("active", "open", "not_looking", name="search_status"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("current_category_id", sa.SmallInteger(), nullable=True),
        sa.Column("grade_assigned_at", sa.DateTime(timezone=True), nullable=True),
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
            "experience_years IS NULL OR (experience_years >= 0 AND experience_years <= 60)",
            name=op.f("ck_candidate_profiles_experience_range"),
        ),
        sa.CheckConstraint(
            "salary_expectation_from IS NULL OR salary_expectation_from > 0",
            name=op.f("ck_candidate_profiles_salary_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["current_category_id"],
            ["categories.id"],
            name=op.f("fk_candidate_profiles_current_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_candidate_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_profiles")),
        sa.UniqueConstraint("public_alias", name=op.f("uq_candidate_profiles_public_alias")),
        sa.UniqueConstraint("user_id", name=op.f("uq_candidate_profiles_user_id")),
    )
    op.create_index(
        op.f("ix_candidate_profiles_current_category_id"),
        "candidate_profiles",
        ["current_category_id"],
        unique=False,
    )
    op.create_table(
        "candidate_skills",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("self_level", sa.SmallInteger(), nullable=True),
        sa.Column("years", sa.Float(), nullable=True),
        sa.Column(
            "source",
            sa.Enum("profile", "survey", "resume", "test", "micro_task", name="skill_source"),
            nullable=False,
        ),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "self_level IS NULL OR self_level BETWEEN 1 AND 5",
            name=op.f("ck_candidate_skills_level_range"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_candidate_skills_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name=op.f("fk_candidate_skills_skill_id_skills"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", "skill_id", name=op.f("pk_candidate_skills")),
    )
    op.create_index(
        op.f("ix_candidate_skills_skill_id"), "candidate_skills", ["skill_id"], unique=False
    )
    op.create_table(
        "educations",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("institution", sa.String(length=300), nullable=False),
        sa.Column("degree", sa.String(length=200), server_default="", nullable=False),
        sa.Column("graduated_year", sa.SmallInteger(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_educations_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_educations")),
    )
    op.create_index(
        op.f("ix_educations_candidate_id"), "educations", ["candidate_id"], unique=False
    )
    op.create_table(
        "privacy_settings",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "show_salary_expectation", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("show_city", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "show_company_names", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "show_fsp_achievements", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "revealed_channels",
            postgresql.ARRAY(sa.String(length=16)),
            server_default=sa.text("'{email,telegram}'::varchar[]"),
            nullable=False,
        ),
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
            name=op.f("fk_privacy_settings_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("candidate_id", name=op.f("pk_privacy_settings")),
    )
    op.create_table(
        "survey_responses",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("specialization_id", sa.SmallInteger(), nullable=False),
        sa.Column("claimed_grade_id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "industry_ids",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{}'::smallint[]"),
            nullable=False,
        ),
        sa.Column(
            "primary_skill_ids",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'::integer[]"),
            nullable=False,
        ),
        sa.Column("experience_years", sa.Float(), nullable=False),
        sa.Column(
            "team_roles",
            postgresql.ARRAY(sa.String(length=32)),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "answers", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("survey_version", sa.String(length=16), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_survey_responses_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claimed_grade_id"],
            ["grades.id"],
            name=op.f("fk_survey_responses_claimed_grade_id_grades"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_survey_responses_specialization_id_specializations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_survey_responses")),
    )
    op.create_index(
        op.f("ix_survey_responses_candidate_id"), "survey_responses", ["candidate_id"], unique=False
    )
    op.create_table(
        "work_experiences",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("company_name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.String(length=200), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ended_on IS NULL OR ended_on >= started_on",
            name=op.f("ck_work_experiences_period_order"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_work_experiences_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_experiences")),
    )
    op.create_index(
        op.f("ix_work_experiences_candidate_id"), "work_experiences", ["candidate_id"], unique=False
    )
    op.create_table(
        "assessment_sessions",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("survey_response_id", sa.Uuid(), nullable=False),
        sa.Column("specialization_id", sa.SmallInteger(), nullable=False),
        sa.Column("target_grade_id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("in_progress", "completed", "abandoned", "expired", name="session_status"),
            nullable=False,
        ),
        sa.Column("seed_salt", sa.String(length=32), nullable=False),
        sa.Column("blueprint", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "pilot_positions",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{}'::smallint[]"),
            nullable=False,
        ),
        sa.Column("theta", sa.Float(), server_default="0", nullable=False),
        sa.Column("theta_se", sa.Float(), server_default="1", nullable=False),
        sa.Column("items_scored", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column(
            "outcome",
            sa.Enum("passed_confident", "passed", "failed", name="session_outcome"),
            nullable=True,
        ),
        sa.Column("resulting_category_id", sa.SmallInteger(), nullable=True),
        sa.Column("suggested_grade_id", sa.SmallInteger(), nullable=True),
        sa.Column(
            "integrity",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("algorithm_version", sa.String(length=16), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_assessment_sessions_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["resulting_category_id"],
            ["categories.id"],
            name=op.f("fk_assessment_sessions_resulting_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id"],
            ["specializations.id"],
            name=op.f("fk_assessment_sessions_specialization_id_specializations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["suggested_grade_id"],
            ["grades.id"],
            name=op.f("fk_assessment_sessions_suggested_grade_id_grades"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["survey_response_id"],
            ["survey_responses.id"],
            name=op.f("fk_assessment_sessions_survey_response_id_survey_responses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_grade_id"],
            ["grades.id"],
            name=op.f("fk_assessment_sessions_target_grade_id_grades"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_sessions")),
    )
    op.create_index(
        op.f("ix_assessment_sessions_candidate_id"),
        "assessment_sessions",
        ["candidate_id"],
        unique=False,
    )
    op.create_table(
        "assessment_items",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("is_pilot", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("instance_seed", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answer_key", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("timed_out", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("presented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("theta_after", sa.Float(), nullable=True),
        sa.Column("se_after", sa.Float(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["item_families.id"],
            name=op.f("fk_assessment_items_family_id_item_families"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["assessment_sessions.id"],
            name=op.f("fk_assessment_items_session_id_assessment_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_items")),
        sa.UniqueConstraint(
            "session_id", "position", name=op.f("uq_assessment_items_session_id_position")
        ),
    )
    op.create_index(
        op.f("ix_assessment_items_family_id"), "assessment_items", ["family_id"], unique=False
    )
    op.create_index(
        op.f("ix_assessment_items_session_id"), "assessment_items", ["session_id"], unique=False
    )
    op.create_table(
        "grade_history",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("from_category_id", sa.SmallInteger(), nullable=True),
        sa.Column("to_category_id", sa.SmallInteger(), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "initial",
                "upgrade",
                "downgrade_voluntary",
                "accepted_lower",
                name="grade_change_reason",
            ),
            nullable=False,
        ),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_grade_history_candidate_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_category_id"],
            ["categories.id"],
            name=op.f("fk_grade_history_from_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["assessment_sessions.id"],
            name=op.f("fk_grade_history_session_id_assessment_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["to_category_id"],
            ["categories.id"],
            name=op.f("fk_grade_history_to_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grade_history")),
    )
    op.create_index(
        op.f("ix_grade_history_candidate_id"), "grade_history", ["candidate_id"], unique=False
    )


def downgrade() -> None:
    """Удаляет таблицы шага 2 и их типы ENUM (autogenerate сам типы не удаляет)."""
    op.drop_index(op.f("ix_grade_history_candidate_id"), table_name="grade_history")
    op.drop_table("grade_history")
    op.drop_index(op.f("ix_assessment_items_session_id"), table_name="assessment_items")
    op.drop_index(op.f("ix_assessment_items_family_id"), table_name="assessment_items")
    op.drop_table("assessment_items")
    op.drop_index(op.f("ix_assessment_sessions_candidate_id"), table_name="assessment_sessions")
    op.drop_table("assessment_sessions")
    op.drop_index(op.f("ix_work_experiences_candidate_id"), table_name="work_experiences")
    op.drop_table("work_experiences")
    op.drop_index(op.f("ix_survey_responses_candidate_id"), table_name="survey_responses")
    op.drop_table("survey_responses")
    op.drop_table("privacy_settings")
    op.drop_index(op.f("ix_educations_candidate_id"), table_name="educations")
    op.drop_table("educations")
    op.drop_index(op.f("ix_candidate_skills_skill_id"), table_name="candidate_skills")
    op.drop_table("candidate_skills")
    op.drop_index(
        op.f("ix_candidate_profiles_current_category_id"), table_name="candidate_profiles"
    )
    op.drop_table("candidate_profiles")
    op.drop_table("specialization_competencies")
    op.drop_index(op.f("ix_item_families_competency_id"), table_name="item_families")
    op.drop_table("item_families")
    op.drop_table("competencies")
    for enum_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
