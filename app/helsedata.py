"""Validering og lagring av helsedata fra iPhone-snarveien.

Samme format og regler som mottakeren i v1, så snarveien bare trenger ny
adresse og nøkkel:

    {"dato": "2026-11-02", "skritt": 8123, "aktiv_energi": "412,5",
     "treningsminutter": 35, "staatimer": 10}
"""

import math
from datetime import date, timedelta
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session

from app.models import Dagsmaling
from app.tid import naa

KILDE = "iphone-snarvei"


def tolk_tall(verdi: Any) -> float | None:
    """Godtar tall, eller tekst med komma eller punktum som desimaltegn.

    Snarveier sender tall som tekst med norsk formatering, for eksempel "1 234,5".
    """
    if verdi is None or verdi == "":
        return None  # feltet er valgfritt
    if isinstance(verdi, bool):  # True er en int i Python, men ikke et gyldig antall skritt
        raise ValueError("må være et tall")
    if isinstance(verdi, int | float):
        tall = float(verdi)
    elif isinstance(verdi, str):
        renset = verdi.strip().replace(" ", "").replace(" ", "").replace(" ", "")
        try:
            tall = float(renset.replace(",", "."))
        except ValueError:
            raise ValueError("må være et tall") from None
    else:
        raise ValueError("må være et tall")
    if not math.isfinite(tall):
        raise ValueError("må være et endelig tall")
    return tall


Tall = Annotated[float | None, BeforeValidator(tolk_tall)]


class Helsedata(BaseModel):
    model_config = ConfigDict(extra="forbid")  # ukjente felt avvises, som i v1

    dato: date
    skritt: Tall = Field(default=None, ge=0, le=200_000)
    aktiv_energi: Tall = Field(default=None, ge=0, le=20_000)  # kcal
    treningsminutter: Tall = Field(default=None, ge=0, le=1_440)
    oppreist_minutter: Tall = Field(default=None, ge=0, le=1_440)  # fra v1, vises ikke lenger
    staatimer: Tall = Field(default=None, ge=0, le=24)  # timer med minst ett minutt stående

    @field_validator("dato")
    @classmethod
    def ikke_i_fremtiden(cls, dato: date) -> date:
        if dato > naa().date() + timedelta(days=1):
            raise ValueError("dato kan ikke være i fremtiden")
        return dato

    def malinger(self) -> dict[str, float]:
        return {
            navn: verdi
            for navn, verdi in self.model_dump(exclude={"dato"}).items()
            if verdi is not None
        }


def forklar(feil: ValidationError) -> str:
    """Første feil, som en kort setning snarveien kan vise."""
    forste = feil.errors()[0]
    felt = ".".join(str(d) for d in forste["loc"]) or "data"
    if forste["type"] == "extra_forbidden":
        return f"ukjent felt: {felt}"
    melding = forste["msg"].removeprefix("Value error, ")
    return f"{felt}: {melding}"


def lagre(db: Session, data: Helsedata, kilde: str = KILDE) -> None:
    """Én rad per måling. Sendes samme dag på nytt, oppdateres verdiene.

    Felt som mangler eller er tomme, lar eksisterende verdi stå.
    """
    tid = naa()
    for maling, verdi in data.malinger().items():
        db.exec(
            insert(Dagsmaling)
            .values(dato=data.dato, maling=maling, verdi=verdi, kilde=kilde, mottatt=tid)
            .on_conflict_do_update(
                index_elements=["dato", "maling"],
                set_={"verdi": verdi, "kilde": kilde, "mottatt": tid},
            )
        )
    db.commit()
