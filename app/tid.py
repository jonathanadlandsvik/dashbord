"""Norsk tid og datoformat, uavhengig av serverens locale (Vercel kjører på engelsk)."""

from datetime import datetime
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")

UKEDAGER = ("mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag")
MANEDER = (
    "januar", "februar", "mars", "april", "mai", "juni",
    "juli", "august", "september", "oktober", "november", "desember",
)  # fmt: skip


def naa() -> datetime:
    return datetime.now(OSLO)


def hilsen(tidspunkt: datetime) -> str:
    if tidspunkt.hour < 5:
        return "God natt"
    if tidspunkt.hour < 10:
        return "God morgen"
    if tidspunkt.hour < 18:
        return "God dag"
    return "God kveld"


def norsk_dato(tidspunkt: datetime) -> str:
    """For eksempel «tirsdag 3. november»."""
    ukedag = UKEDAGER[tidspunkt.weekday()]
    maned = MANEDER[tidspunkt.month - 1]
    return f"{ukedag} {tidspunkt.day}. {maned}"
