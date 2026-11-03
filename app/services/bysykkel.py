"""Ledige bysykler fra Trondheim Bysykkel (GBFS 2.x hos Urban Sharing)."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.services.http import TIMEOUT, user_agent

BASE = "https://gbfs.urbansharing.com/trondheimbysykkel.no"


@dataclass(frozen=True)
class Stasjon:
    navn: str
    sykler: int
    elsykler: int
    ledige_plasser: int
    i_drift: bool
    rapportert: datetime | None


def tolk(status: dict, info: dict, stasjon_id: str) -> Stasjon:
    rad = next((s for s in status["data"]["stations"] if s["station_id"] == stasjon_id), None)
    if rad is None:
        raise LookupError(f"Fant ikke stasjon {stasjon_id}")
    navn = next(
        (s["name"] for s in info["data"]["stations"] if s["station_id"] == stasjon_id),
        f"Stasjon {stasjon_id}",
    )
    typer = {t["vehicle_type_id"]: t["count"] for t in rad.get("vehicle_types_available", [])}
    sykler = typer.get("bike", rad.get("num_bikes_available", 0) - typer.get("ebike", 0))
    rapportert = rad.get("last_reported")
    return Stasjon(
        navn=navn,
        sykler=sykler,
        elsykler=typer.get("ebike", 0),
        ledige_plasser=rad.get("num_docks_available", 0),
        i_drift=bool(rad.get("is_renting", True)),
        rapportert=datetime.fromtimestamp(rapportert, UTC) if rapportert else None,
    )


async def hent_stasjon(settings: Settings) -> Stasjon:
    async with httpx.AsyncClient(
        timeout=TIMEOUT, headers={"User-Agent": user_agent(settings)}
    ) as klient:
        status, info = await asyncio.gather(
            klient.get(f"{BASE}/station_status.json"),
            klient.get(f"{BASE}/station_information.json"),
        )
    status.raise_for_status()
    info.raise_for_status()
    return tolk(status.json(), info.json(), settings.bysykkel_stasjon_id)
