"""Tabeller for innlogging: passkeys, sesjoner, utfordringer, koder og forsøk

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tidsstempel(navn: str) -> sa.Column:
    return sa.Column(navn, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "passkeys",
        sa.Column("id", sa.LargeBinary(), primary_key=True),
        sa.Column("offentlig_nokkel", sa.LargeBinary(), nullable=False),
        sa.Column("signaturteller", sa.Integer(), nullable=False),
        sa.Column("navn", sa.String(length=60), nullable=False),
        _tidsstempel("opprettet"),
        sa.Column("sist_brukt", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "sesjoner",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        _tidsstempel("opprettet"),
        sa.Column("utloper", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sist_sett", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "utfordringer",
        sa.Column("token_hash", sa.String(length=64), primary_key=True),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("formal", sa.String(length=20), nullable=False),
        sa.Column("utloper", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("formal IN ('registrering', 'innlogging')", name="formal_gyldig"),
    )
    op.create_table(
        "gjenopprettingskoder",
        sa.Column("kode_hash", sa.String(length=64), primary_key=True),
        _tidsstempel("opprettet"),
        sa.Column("brukt", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "innloggingsforsok",
        sa.Column("id", sa.Integer(), primary_key=True),
        _tidsstempel("tidspunkt"),
        sa.Column("metode", sa.String(length=20), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("innloggingsforsok")
    op.drop_table("gjenopprettingskoder")
    op.drop_table("utfordringer")
    op.drop_table("sesjoner")
    op.drop_table("passkeys")
