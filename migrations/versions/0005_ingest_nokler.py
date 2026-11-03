"""API-nøkler for iPhone-snarveien

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_nokler",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("navn", sa.String(length=60), nullable=False, unique=True),
        sa.Column("nokkel_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "opprettet",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sist_brukt", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tilbakekalt", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingest_nokler")
