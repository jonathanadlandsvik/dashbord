"""Tabellene. Endringer her må alltid følges av en ny Alembic-migrasjon.

Reglene som må holde uansett hvem som skriver til databasen, ligger som
CHECK-constraints i Postgres og ikke bare i Python.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    SmallInteger,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Field, SQLModel

ALLE_DAGER = [0, 1, 2, 3, 4, 5, 6]  # 0 = mandag, som i Pythons date.weekday()
HVERDAGER = [0, 1, 2, 3, 4]


def _tidsstempel() -> Column:
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Vane(SQLModel, table=True):
    """Én versjon av en vane.

    Endres et mål, avsluttes raden (aktiv_til) og en ny rad med samme nøkkel
    legges inn. Da vurderes tidligere uker mot målet som gjaldt den gangen.
    """

    __tablename__ = "vaner"
    __table_args__ = (
        UniqueConstraint("nokkel", "aktiv_fra", name="vaner_nokkel_aktiv_fra_key"),
        CheckConstraint("ukemal >= 1 AND ukemal <= cardinality(ukedager)", name="ukemal_gyldig"),
        CheckConstraint(
            "cardinality(ukedager) >= 1 AND ukedager <@ ARRAY[0,1,2,3,4,5,6]::smallint[]",
            name="ukedager_gyldige",
        ),
        CheckConstraint("aktiv_til IS NULL OR aktiv_til > aktiv_fra", name="aktiv_periode_gyldig"),
    )

    id: int | None = Field(default=None, primary_key=True)
    nokkel: str = Field(max_length=40)
    navn: str = Field(max_length=60)
    formulering: str = Field(max_length=120)
    ukemal: int
    ukedager: list[int] = Field(sa_column=Column(ARRAY(SmallInteger), nullable=False))
    sortering: int = 0
    aktiv_fra: date
    aktiv_til: date | None = None


class Avkrysning(SQLModel, table=True):
    """At en vane er gjort en bestemt dag. Fjernes avkrysningen, slettes raden."""

    __tablename__ = "avkrysninger"

    vane_id: int = Field(foreign_key="vaner.id", primary_key=True, ondelete="RESTRICT")
    dato: date = Field(primary_key=True)
    registrert: datetime | None = Field(default=None, sa_column=_tidsstempel())


class Ukeoppsummering(SQLModel, table=True):
    """Søndagens oppsummering: skjermtid og én setning om hva som justeres."""

    __tablename__ = "ukeoppsummeringer"
    __table_args__ = (
        CheckConstraint("extract(isodow from uke_start) = 1", name="uke_start_er_mandag"),
        CheckConstraint("skjermtid_timer BETWEEN 0 AND 24", name="skjermtid_gyldig"),
    )

    uke_start: date = Field(primary_key=True)
    skjermtid_timer: Decimal | None = Field(default=None, max_digits=3, decimal_places=1)
    refleksjon: str | None = Field(default=None, max_length=500)
    oppdatert: datetime | None = Field(default=None, sa_column=_tidsstempel())


class Dagsmaling(SQLModel, table=True):
    """Ett tall for én dag, for eksempel skritt fra iPhone-snarveien.

    Generell form (måling + verdi) i stedet for én kolonne per tall, så en ny
    type måling ikke krever en migrasjon.
    """

    __tablename__ = "dagsmalinger"
    __table_args__ = (CheckConstraint("verdi >= 0", name="verdi_ikke_negativ"),)

    dato: date = Field(primary_key=True)
    maling: str = Field(primary_key=True, max_length=40)
    verdi: float
    kilde: str = Field(max_length=40)
    mottatt: datetime | None = Field(default=None, sa_column=_tidsstempel())


# ---------- Innlogging (fase 3) ----------
# Appen har én bruker, så det finnes ingen brukertabell. Hemmeligheter lagres
# aldri i klartekst: sesjoner, utfordringer og gjenopprettingskoder lagres som
# SHA-256 av en tilfeldig verdi, og bare brukeren har selve verdien.


class Passkey(SQLModel, table=True):
    """En registrert passkey, for eksempel Face ID på iPhonen."""

    __tablename__ = "passkeys"

    id: bytes = Field(primary_key=True)  # credential id fra autentikatoren
    offentlig_nokkel: bytes
    signaturteller: int = 0
    navn: str = Field(max_length=60)
    opprettet: datetime | None = Field(default=None, sa_column=_tidsstempel())
    sist_brukt: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class Sesjon(SQLModel, table=True):
    """En innlogget nettleser. Cookien har tokenet, databasen bare hashen."""

    __tablename__ = "sesjoner"

    token_hash: str = Field(primary_key=True, max_length=64)
    opprettet: datetime | None = Field(default=None, sa_column=_tidsstempel())
    utloper: datetime = Field(sa_type=DateTime(timezone=True))
    sist_sett: datetime = Field(sa_type=DateTime(timezone=True))


class Utfordring(SQLModel, table=True):
    """En WebAuthn-challenge som kan brukes én gang, innen noen minutter."""

    __tablename__ = "utfordringer"
    __table_args__ = (
        CheckConstraint("formal IN ('registrering', 'innlogging')", name="formal_gyldig"),
    )

    token_hash: str = Field(primary_key=True, max_length=64)
    challenge: bytes
    formal: str = Field(max_length=20)
    utloper: datetime = Field(sa_type=DateTime(timezone=True))


class Gjenopprettingskode(SQLModel, table=True):
    """Engangskoder i tilfelle telefonen blir borte."""

    __tablename__ = "gjenopprettingskoder"

    kode_hash: str = Field(primary_key=True, max_length=64)
    opprettet: datetime | None = Field(default=None, sa_column=_tidsstempel())
    brukt: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


class Innloggingsforsok(SQLModel, table=True):
    """Mislykkede forsøk, brukt til å bremse gjetting."""

    __tablename__ = "innloggingsforsok"

    id: int | None = Field(default=None, primary_key=True)
    tidspunkt: datetime | None = Field(default=None, sa_column=_tidsstempel())
    metode: str = Field(max_length=20)


# ---------- Cache for eksterne tjenester (fase 4) ----------


class ApiCache(SQLModel, table=True):
    """Siste svar fra en ekstern tjeneste, så vi ikke spør oftere enn nødvendig.

    Yr (MET) krever at klienter respekterer Expires og bruker If-Modified-Since.
    På Vercel husker ikke funksjonen noe mellom kall, så cachen må ligge her.
    """

    __tablename__ = "api_cache"

    nokkel: str = Field(primary_key=True, max_length=100)
    innhold: dict = Field(sa_column=Column(JSONB, nullable=False))
    utloper: datetime = Field(sa_type=DateTime(timezone=True))
    sist_endret: str | None = Field(default=None, max_length=64)  # Last-Modified fra tjenesten
    hentet: datetime | None = Field(default=None, sa_column=_tidsstempel())
