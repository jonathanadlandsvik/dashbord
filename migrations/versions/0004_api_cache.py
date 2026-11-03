"""Cache for svar fra eksterne tjenester (Yr)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_cache",
        sa.Column("nokkel", sa.String(length=100), primary_key=True),
        sa.Column("innhold", postgresql.JSONB(), nullable=False),
        sa.Column("utloper", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sist_endret", sa.String(length=64), nullable=True),
        sa.Column(
            "hentet", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("api_cache")
