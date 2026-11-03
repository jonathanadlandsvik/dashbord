"""Værmelding fra Yr (MET Norway, locationforecast 2.0 compact).

MET sine vilkår: identifiser deg med User-Agent, maks 4 desimaler i koordinatene,
respekter Expires og bruk If-Modified-Since. Svaret caches derfor i databasen.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from sqlmodel import Session

from app.config import Settings
from app.models import ApiCache
from app.services.http import TIMEOUT, user_agent
from app.tid import OSLO

URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
ANTALL_TIMER = 12

SYMBOLER = {
    "clearsky": "Klarvær",
    "fair": "Lettskyet",
    "partlycloudy": "Delvis skyet",
    "cloudy": "Skyet",
    "fog": "Tåke",
    "lightrainshowers": "Lette regnbyger",
    "rainshowers": "Regnbyger",
    "heavyrainshowers": "Kraftige regnbyger",
    "lightrain": "Lett regn",
    "rain": "Regn",
    "heavyrain": "Kraftig regn",
    "lightsleetshowers": "Lette sluddbyger",
    "sleetshowers": "Sluddbyger",
    "heavysleetshowers": "Kraftige sluddbyger",
    "lightsleet": "Lett sludd",
    "sleet": "Sludd",
    "heavysleet": "Kraftig sludd",
    "lightsnowshowers": "Lette snøbyger",
    "snowshowers": "Snøbyger",
    "heavysnowshowers": "Kraftige snøbyger",
    "lightsnow": "Lett snø",
    "snow": "Snø",
    "heavysnow": "Kraftig snø",
}


@dataclass(frozen=True)
class Time:
    klokke: str  # "16"
    temperatur: float
    nedbor: float  # mm neste time


@dataclass(frozen=True)
class Vaer:
    temperatur: float
    beskrivelse: str
    vind: float  # m/s
    timer: list[Time]
    nedbor_6t: float
    utdatert: bool = False  # True hvis Yr ikke svarte og vi viser forrige svar


def beskriv(symbolkode: str) -> str:
    """'lightrainshowersandthunder_day' -> 'Lette regnbyger og torden'."""
    kode = symbolkode.split("_")[0]
    torden = kode.endswith("andthunder")
    kode = kode.removesuffix("andthunder")
    tekst = SYMBOLER.get(kode, "Ukjent vær")
    return f"{tekst} og torden" if torden else tekst


def tolk(data: dict, naa: datetime) -> Vaer:
    denne_timen = naa.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    serie = [
        punkt
        for punkt in data["properties"]["timeseries"]
        if datetime.fromisoformat(punkt["time"].replace("Z", "+00:00")) >= denne_timen
    ]
    if not serie:
        raise ValueError("Værmeldingen har ingen tidspunkter fra nå av")

    forste = serie[0]["data"]
    symbol = forste.get("next_1_hours") or forste.get("next_6_hours") or forste.get("next_12_hours")
    timer = []
    for punkt in serie:
        neste = punkt["data"].get("next_1_hours")
        if neste is None:
            break  # lenger frem gir MET bare 6-timers intervaller
        tid = datetime.fromisoformat(punkt["time"].replace("Z", "+00:00")).astimezone(OSLO)
        timer.append(
            Time(
                klokke=tid.strftime("%H"),
                temperatur=punkt["data"]["instant"]["details"]["air_temperature"],
                nedbor=neste["details"].get("precipitation_amount", 0.0),
            )
        )
        if len(timer) == ANTALL_TIMER:
            break

    detaljer = forste["instant"]["details"]
    return Vaer(
        temperatur=detaljer["air_temperature"],
        beskrivelse=beskriv(symbol["summary"]["symbol_code"]) if symbol else "Ukjent vær",
        vind=detaljer.get("wind_speed", 0.0),
        timer=timer,
        nedbor_6t=round(sum(t.nedbor for t in timer[:6]), 1),
    )


def _utloper(svar: httpx.Response, naa: datetime) -> datetime:
    try:
        return parsedate_to_datetime(svar.headers["Expires"])
    except (KeyError, TypeError, ValueError):
        return naa + timedelta(minutes=30)


def hent_vaer(db: Session, settings: Settings, naa: datetime, klient: httpx.Client) -> Vaer:
    lat, lon = round(settings.vaer_lat, 4), round(settings.vaer_lon, 4)
    nokkel = f"yr:{lat},{lon}"
    cache = db.get(ApiCache, nokkel)

    if cache is not None and cache.utloper > naa:
        return tolk(cache.innhold, naa)

    headere = {"User-Agent": user_agent(settings)}
    if cache is not None and cache.sist_endret:
        headere["If-Modified-Since"] = cache.sist_endret

    try:
        svar = klient.get(URL, params={"lat": lat, "lon": lon}, headers=headere, timeout=TIMEOUT)
    except httpx.HTTPError:
        if cache is None:
            raise
        return _utdatert(tolk(cache.innhold, naa))

    if svar.status_code == 304 and cache is not None:
        innhold = cache.innhold  # uendret siden sist
    elif svar.is_success:
        innhold = svar.json()
    elif cache is not None:
        return _utdatert(tolk(cache.innhold, naa))
    else:
        svar.raise_for_status()

    db.merge(
        ApiCache(
            nokkel=nokkel,
            innhold=innhold,
            utloper=_utloper(svar, naa),
            sist_endret=svar.headers.get("Last-Modified") or (cache.sist_endret if cache else None),
            hentet=naa,  # merge oppdaterer alle felt, så denne må settes eksplisitt
        )
    )
    db.commit()
    return tolk(innhold, naa)


def _utdatert(vaer: Vaer) -> Vaer:
    return Vaer(**{**vaer.__dict__, "utdatert": True})
