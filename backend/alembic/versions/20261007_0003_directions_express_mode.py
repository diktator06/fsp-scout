"""Направления специализаций, режим теста и признак гросс у ожиданий кандидата

Ревизия: 0003
Предыдущая: 0002
Создана: 2026-10-07 09:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ASSESSMENT_MODE = postgresql.ENUM("full", "express", name="assessment_mode", create_type=False)


def upgrade() -> None:
    """Добавляет поля по итогам встречи с менторами.

    `add_column` не создаёт тип ENUM в PostgreSQL сам (в отличие от `create_table`),
    поэтому тип режима теста создаётся явно до добавления столбца.
    """
    ASSESSMENT_MODE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "assessment_sessions",
        sa.Column("mode", ASSESSMENT_MODE, server_default="full", nullable=False),
    )
    op.add_column(
        "candidate_profiles",
        sa.Column(
            "salary_expectation_gross", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
    )
    op.add_column(
        "specializations",
        sa.Column(
            "direction_code", sa.String(length=32), server_default="development", nullable=False
        ),
    )
    op.add_column(
        "specializations",
        sa.Column(
            "direction_name", sa.String(length=64), server_default="Разработка", nullable=False
        ),
    )


def downgrade() -> None:
    """Удаляет добавленные столбцы и тип режима теста."""
    op.drop_column("specializations", "direction_name")
    op.drop_column("specializations", "direction_code")
    op.drop_column("candidate_profiles", "salary_expectation_gross")
    op.drop_column("assessment_sessions", "mode")
    ASSESSMENT_MODE.drop(op.get_bind(), checkfirst=True)
