"""Boksene på forsiden. Hver lastes for seg med HTMX, så en treg tjeneste
ikke holder igjen de andre, og en feil bare påvirker sin egen boks."""

import logging
from datetime import timedelta
from functools import lru_cache

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlmodel import select

from app.auth import AppSettings, DbSesjon, Innlogget
from app.models import Dagsmaling
from app.services import bysykkel, kalender, yr
from app.templating import templates
from app.tid import naa

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/boks")


@lru_cache
def _yr_klient() -> httpx.Client:
    return httpx.Client(timeout=yr.TIMEOUT)


def _feil(request: Request, tittel: str, melding: str) -> HTMLResponse:
    # Status 200 med en melding i boksen: HTMX bytter bare inn innhold ved 2xx.
    return templates.TemplateResponse(
        request, "bokser/feil.html", {"tittel": tittel, "melding": melding}
    )


@router.get("/vaer", response_class=HTMLResponse)
def vaer(request: Request, _: Innlogget, db: DbSesjon, settings: AppSettings) -> HTMLResponse:
    try:
        data = yr.hent_vaer(db, settings, naa(), _yr_klient())
    except Exception:
        logger.exception("Kunne ikke hente vær")
        return _feil(request, "Vær", "Fikk ikke hentet værmeldingen akkurat nå.")
    return templates.TemplateResponse(request, "bokser/vaer.html", {"vaer": data})


@router.get("/bysykkel", response_class=HTMLResponse)
async def sykkel(request: Request, _: Innlogget, settings: AppSettings) -> HTMLResponse:
    try:
        stasjon = await bysykkel.hent_stasjon(settings)
    except Exception:
        logger.exception("Kunne ikke hente bysykkel")
        return _feil(request, "Bysykkel", "Fikk ikke hentet bysykler akkurat nå.")
    return templates.TemplateResponse(request, "bokser/bysykkel.html", {"stasjon": stasjon})


@router.get("/kalender", response_class=HTMLResponse)
async def kalender_boks(request: Request, _: Innlogget, settings: AppSettings) -> HTMLResponse:
    try:
        hendelser = await kalender.hent_dagens(settings, naa())
    except kalender.KalenderTilgangFeil:
        logger.warning("Google-tilgangen er utløpt eller mangler")
        return _feil(
            request,
            "Kalender",
            "Google-tilgangen er utløpt. Lag et nytt refresh token og oppdater "
            "GOOGLE_REFRESH_TOKEN i Vercel.",
        )
    except Exception:
        logger.exception("Kunne ikke hente kalender")
        return _feil(request, "Kalender", "Fikk ikke hentet kalenderen akkurat nå.")
    return templates.TemplateResponse(request, "bokser/kalender.html", {"hendelser": hendelser})


@router.get("/aktivitet", response_class=HTMLResponse)
def aktivitet(request: Request, _: Innlogget, db: DbSesjon) -> HTMLResponse:
    i_gaar = naa().date() - timedelta(days=1)
    rader = db.exec(select(Dagsmaling).where(Dagsmaling.dato == i_gaar)).all()
    malinger = {r.maling: r.verdi for r in rader}
    return templates.TemplateResponse(request, "bokser/aktivitet.html", {"m": malinger})
