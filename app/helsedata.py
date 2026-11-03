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


def tolk_liste(verdi: Any) -> list[float] | None:
    """En liste med tall, som JSON-liste eller som tekst med ett tall per linje.

    Når Snarveier setter en liste inn i et tekstfelt, skilles elementene med linjeskift.
    """
    if verdi is None or verdi == "":
        return None
    if isinstance(verdi, str):
        deler = [d for d in verdi.replace(";", "\n").splitlines() if d.strip()]
    elif isinstance(verdi, list):
        deler = verdi
    else:
        raise ValueError("må være en liste med tall")
    if len(deler) > 25:  # 24 timer, pluss én hvis perioden tar med midnatt
        raise ValueError("kan ha maks 25 verdier")
    tall = [tolk_tall(d) for d in deler]
    if any(t is None or not 0 <= t <= 60 for t in tall):
        raise ValueError("hver verdi må være minutter mellom 0 og 60")
    return tall  # type: ignore[return-value]


class Helsedata(BaseModel):
    model_config = ConfigDict(extra="forbid")  # ukjente felt avvises, som i v1

    dato: date
    skritt: Tall = Field(default=None, ge=0, le=200_000)
    aktiv_energi: Tall = Field(default=None, ge=0, le=20_000)  # kcal
    treningsminutter: Tall = Field(default=None, ge=0, le=1_440)
    oppreist_minutter: Tall = Field(default=None, ge=0, le=1_440)  # fra v1, vises ikke lenger
    staatimer: Tall = Field(default=None, ge=0, le=24)  # timer med minst ett minutt stående
    # Ståtid gruppert per time. Snarveier kan ikke lese ståtimer direkte, men en time
    # med minst ett minutt stående er nøyaktig det ståringen på klokka teller.
    staatid_per_time: Annotated[list[float] | None, BeforeValidator(tolk_liste)] = None

    @field_validator("dato")
    @classmethod
    def ikke_i_fremtiden(cls, dato: date) -> date:
        if dato > naa().date() + timedelta(days=1):
            raise ValueError("dato kan ikke være i fremtiden")
        return dato

    def malinger(self) -> dict[str, float]:
        verdier = self.model_dump(exclude={"dato", "staatid_per_time"})
        if self.staatid_per_time is not None and self.staatimer is None:
            verdier["staatimer"] = float(
                sum(1 for minutter in self.staatid_per_time if minutter > 0)
            )
        return {navn: verdi for navn, verdi in verdier.items() if verdi is not None}


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
