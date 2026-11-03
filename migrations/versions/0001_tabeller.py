"""Lag tabellene for vaner, avkrysninger, ukeoppsummeringer og dagsmålinger

Revision ID: 0001
Revises:
Create Date: 2026-11-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vaner",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nokkel", sa.String(length=40), nullable=False),
        sa.Column("navn", sa.String(length=60), nullable=False),
        sa.Column("formulering", sa.String(length=120), nullable=False),
        sa.Column("ukemal", sa.Integer(), nullable=False),
        sa.Column("ukedager", postgresql.ARRAY(sa.SmallInteger()), nullable=False),
        sa.Column("sortering", sa.Integer(), nullable=False),
        sa.Column("aktiv_fra", sa.Date(), nullable=False),
        sa.Column("aktiv_til", sa.Date(), nullable=True),
        sa.UniqueConstraint("nokkel", "aktiv_fra", name="vaner_nokkel_aktiv_fra_key"),
        sa.CheckConstraint("ukemal >= 1 AND ukemal <= cardinality(ukedager)", name="ukemal_gyldig"),
        sa.CheckConstraint(
            "cardinality(ukedager) >= 1 AND ukedager <@ ARRAY[0,1,2,3,4,5,6]::smallint[]",
            name="ukedager_gyldige",
        ),
        sa.CheckConstraint(
            "aktiv_til IS NULL OR aktiv_til > aktiv_fra", name="aktiv_periode_gyldig"
        ),
    )

    op.create_table(
        "avkrysninger",
        sa.Column(
            "vane_id",
            sa.Integer(),
            sa.ForeignKey("vaner.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("dato", sa.Date(), primary_key=True),
        sa.Column(
            "registrert",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "ukeoppsummeringer",
        sa.Column("uke_start", sa.Date(), primary_key=True),
        sa.Column("skjermtid_timer", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("refleksjon", sa.String(length=500), nullable=True),
        sa.Column(
            "oppdatert",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("extract(isodow from uke_start) = 1", name="uke_start_er_mandag"),
        sa.CheckConstraint("skjermtid_timer BETWEEN 0 AND 24", name="skjermtid_gyldig"),
    )

    op.create_table(
        "dagsmalinger",
        sa.Column("dato", sa.Date(), primary_key=True),
        sa.Column("maling", sa.String(length=40), primary_key=True),
        sa.Column("verdi", sa.Float(), nullable=False),
        sa.Column("kilde", sa.String(length=40), nullable=False),
        sa.Column(
            "mottatt",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("verdi >= 0", name="verdi_ikke_negativ"),
    )


def downgrade() -> None:
    op.drop_table("dagsmalinger")
    op.drop_table("ukeoppsummeringer")
    op.drop_table("avkrysninger")
    op.drop_table("vaner")
