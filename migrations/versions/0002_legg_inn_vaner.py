"""Legg inn de seks vanene fra november 2026

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-03
"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

START = date(2026, 11, 2)  # mandagen målene ble satt
ALLE = [0, 1, 2, 3, 4, 5, 6]
HVERDAGER = [0, 1, 2, 3, 4]

VANER = [
    ("instagram", "Instagram", "Under 30 minutter på Instagram", 7, ALLE),
    ("opp", "Opp med en gang", "Ute av senga innen 5 minutter etter alarmen", 5, HVERDAGER),
    (
        "mobilfri-morgen",
        "Mobilfri morgen",
        "Lot mobilen ligge på rommet til etter frokost",
        7,
        ALLE,
    ),
    ("kreatin", "Kreatin", "Tok kreatin", 7, ALLE),
    ("trening", "Trening", "Trente", 2, ALLE),
    ("lese-gitar", "Lese eller gitar", "Leste eller spilte gitar i minst 15 minutter", 5, ALLE),
]

# En lett kopi av tabellen, så migrasjonen ikke avhenger av app.models
# (modellene kan endre seg senere, migrasjonen skal ikke det).
vaner = sa.table(
    "vaner",
    sa.column("nokkel", sa.String),
    sa.column("navn", sa.String),
    sa.column("formulering", sa.String),
    sa.column("ukemal", sa.Integer),
    sa.column("ukedager", postgresql.ARRAY(sa.SmallInteger)),
    sa.column("sortering", sa.Integer),
    sa.column("aktiv_fra", sa.Date),
)


def upgrade() -> None:
    op.bulk_insert(
        vaner,
        [
            {
                "nokkel": nokkel,
                "navn": navn,
                "formulering": formulering,
                "ukemal": ukemal,
                "ukedager": dager,
                "sortering": nummer,
                "aktiv_fra": START,
            }
            for nummer, (nokkel, navn, formulering, ukemal, dager) in enumerate(VANER, start=1)
        ],
    )


def downgrade() -> None:
    nokler = [nokkel for nokkel, *_ in VANER]
    op.execute(vaner.delete().where(vaner.c.nokkel.in_(nokler)).where(vaner.c.aktiv_fra == START))
