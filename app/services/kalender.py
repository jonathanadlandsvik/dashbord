"""Dagens avtaler fra Google Calendar, hentet direkte med HTTP.

Bruker den samme OAuth-klienten og det samme refresh tokenet som v1. Access
tokenet varer en time og holdes i minnet så lenge funksjonen lever.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.parse import quote

import httpx

from app.config import Settings
from app.services.http import TIMEOUT
from app.tid import OSLO

TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (en adresse, ikke et passord)
API = "https://www.googleapis.com/calendar/v3"
UTELAT = {"Ukenumre"}  # kalendere som ikke er avtaler

_token: dict[str, float | str] = {}


class KalenderTilgangFeil(Exception):
    """Refresh tokenet er utløpt eller trukket tilbake."""


@dataclass(frozen=True)
class Hendelse:
    tid: str  # "09:15", "Hele dagen" eller "Pågår"
    tittel: str
    sortering: datetime


async def _access_token(klient: httpx.AsyncClient, settings: Settings) -> str:
    if _token and float(_token["utloper"]) > time.monotonic():
        return str(_token["verdi"])
    if not (
        settings.google_client_id
        and settings.google_client_secret
        and settings.google_refresh_token
    ):
        raise KalenderTilgangFeil("Google-nøklene er ikke satt")
    svar = await klient.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret.get_secret_value(),
            "refresh_token": settings.google_refresh_token.get_secret_value(),
        },
    )
    if svar.status_code in (400, 401):
        raise KalenderTilgangFeil("Google avviste refresh tokenet")
    svar.raise_for_status()
    data = svar.json()
    _token["verdi"] = data["access_token"]
    _token["utloper"] = time.monotonic() + int(data.get("expires_in", 3600)) - 60
    return data["access_token"]


def _tolk_hendelse(hendelse: dict, dagstart: datetime) -> Hendelse | None:
    if hendelse.get("status") == "cancelled":
        return None
    start = hendelse.get("start", {})
    tittel = hendelse.get("summary") or "(uten tittel)"
    if "dateTime" in start:
        tidspunkt = datetime.fromisoformat(start["dateTime"]).astimezone(OSLO)
        tekst = tidspunkt.strftime("%H:%M") if tidspunkt >= dagstart else "Pågår"
        return Hendelse(tid=tekst, tittel=tittel, sortering=max(tidspunkt, dagstart))
    if "date" in start:
        # Heldagshendelser sorteres først.
        return Hendelse(tid="Hele dagen", tittel=tittel, sortering=dagstart - timedelta(seconds=1))
    return None


def tolk(svar_per_kalender: list[dict], dag: date) -> list[Hendelse]:
    dagstart = datetime.combine(dag, datetime.min.time(), tzinfo=OSLO)
    hendelser = [
        h
        for svar in svar_per_kalender
        for item in svar.get("items", [])
        if (h := _tolk_hendelse(item, dagstart)) is not None
    ]
    return sorted(hendelser, key=lambda h: h.sortering)


async def hent_dagens(settings: Settings, naa: datetime) -> list[Hendelse]:
    dagstart = naa.astimezone(OSLO).replace(hour=0, minute=0, second=0, microsecond=0)
    params = {
        "timeMin": dagstart.isoformat(),
        "timeMax": (dagstart + timedelta(days=1)).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "50",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as klient:
        token = await _access_token(klient, settings)
        headere = {"Authorization": f"Bearer {token}"}
        liste = await klient.get(f"{API}/users/me/calendarList", headers=headere)
        if liste.status_code == 401:
            _token.clear()
            raise KalenderTilgangFeil("Access tokenet ble avvist")
        liste.raise_for_status()
        kalendere = [
            k["id"]
            for k in liste.json().get("items", [])
            if k.get("summary") not in UTELAT and not k.get("hidden")
        ]
        svar = await asyncio.gather(
            *(
                klient.get(
                    f"{API}/calendars/{quote(k, safe='')}/events", headers=headere, params=params
                )
                for k in kalendere
            )
        )
    for s in svar:
        s.raise_for_status()
    return tolk([s.json() for s in svar], dagstart.date())
