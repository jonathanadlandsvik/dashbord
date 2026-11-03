"""Innlogging, oppsett av passkeys og utlogging."""

import hmac
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app import passkeys
from app.auth import (
    AppSettings,
    DbSesjon,
    InnloggetMedCsrf,
    Ugyldig,
    avslutt_sesjon,
    bruk_utfordring,
    csrf_token,
    innlogget_sesjon,
    krev_csrf,
    krev_ikke_sperret,
    lagre_utfordring,
    opprett_sesjon,
    registrer_feil,
    rydd_opp,
)
from app.config import Settings
from app.templating import templates

router = APIRouter()


class StartRegistrering(BaseModel):
    setup_token: str | None = None


class FullforRegistrering(BaseModel):
    utfordring: str = Field(max_length=100)
    credential: dict
    navn: str = Field(default="iPhone", min_length=1, max_length=60)
    setup_token: str | None = None


class FullforInnlogging(BaseModel):
    utfordring: str = Field(max_length=100)
    credential: dict


# ---------- Sider ----------


@router.get("/logg-inn", response_class=HTMLResponse)
def logg_inn_side(request: Request, db: DbSesjon, settings: AppSettings) -> Response:
    if innlogget_sesjon(request, db, settings):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "logg_inn.html", {"har_passkeys": passkeys.finnes_passkeys(db)}
    )


@router.get("/oppsett", response_class=HTMLResponse)
def oppsett_side(request: Request, db: DbSesjon, settings: AppSettings) -> Response:
    sesjon = innlogget_sesjon(request, db, settings)
    forste_gang = not passkeys.finnes_passkeys(db)
    if sesjon is None and not forste_gang:
        return RedirectResponse("/logg-inn", status_code=303)
    return templates.TemplateResponse(
        request,
        "oppsett.html",
        {
            "forste_gang": forste_gang,
            "csrf": csrf_token(request, sesjon) if sesjon else "",
        },
    )


# ---------- Registrering ----------


async def _krev_lov_til_registrering(
    request: Request, db: DbSesjon, settings: Settings, setup_token: str | None
) -> bool:
    """Returnerer True hvis dette er den første passkeyen.

    Første passkey krever engangstokenet fra miljøvariabelen. Senere passkeys
    krever at du allerede er innlogget, så et lekket token alene er verdiløst.
    """
    if not passkeys.finnes_passkeys(db):
        forventet = settings.setup_token.get_secret_value() if settings.setup_token else ""
        if not forventet or not setup_token or not hmac.compare_digest(setup_token, forventet):
            registrer_feil(db, "setup-token")
            raise Ugyldig("Feil oppsettkode.", 403)
        return True
    sesjon = innlogget_sesjon(request, db, settings)
    if sesjon is None:
        raise Ugyldig("Du må være logget inn for å legge til en passkey.", 403)
    await krev_csrf(request, sesjon)
    return False


@router.post("/auth/registrering/start")
async def registrering_start(
    request: Request, data: StartRegistrering, db: DbSesjon, settings: AppSettings
) -> JSONResponse:
    krev_ikke_sperret(db)
    await _krev_lov_til_registrering(request, db, settings, data.setup_token)
    challenge, valg = passkeys.registreringsvalg(db, settings)
    token = lagre_utfordring(db, challenge, "registrering")
    return JSONResponse({"utfordring": token, "valg": valg})


@router.post("/auth/registrering/fullfor")
async def registrering_fullfor(
    request: Request, data: FullforRegistrering, db: DbSesjon, settings: AppSettings
) -> JSONResponse:
    krev_ikke_sperret(db)
    forste = await _krev_lov_til_registrering(request, db, settings, data.setup_token)
    challenge = bruk_utfordring(db, data.utfordring, "registrering")
    passkeys.lagre_passkey(db, settings, data.credential, challenge, data.navn.strip())
    if not forste:
        return JSONResponse({"ok": True, "neste": "/"})
    koder = passkeys.lag_gjenopprettingskoder(db)
    svar = JSONResponse({"ok": True, "koder": koder, "neste": "/"})
    opprett_sesjon(db, svar, settings)
    return svar


# ---------- Innlogging ----------


@router.post("/auth/innlogging/start")
def innlogging_start(db: DbSesjon, settings: AppSettings) -> JSONResponse:
    rydd_opp(db)
    krev_ikke_sperret(db)
    if not passkeys.finnes_passkeys(db):
        raise Ugyldig("Ingen passkey er satt opp ennå.")
    challenge, valg = passkeys.innloggingsvalg(db, settings)
    token = lagre_utfordring(db, challenge, "innlogging")
    return JSONResponse({"utfordring": token, "valg": valg})


@router.post("/auth/innlogging/fullfor")
def innlogging_fullfor(
    data: FullforInnlogging, db: DbSesjon, settings: AppSettings
) -> JSONResponse:
    krev_ikke_sperret(db)
    challenge = bruk_utfordring(db, data.utfordring, "innlogging")
    try:
        passkeys.verifiser_innlogging(db, settings, data.credential, challenge)
    except Ugyldig:
        registrer_feil(db, "passkey")
        raise
    svar = JSONResponse({"ok": True, "neste": "/"})
    opprett_sesjon(db, svar, settings)
    return svar


@router.post("/logg-inn/kode", response_class=HTMLResponse)
def logg_inn_med_kode(
    request: Request,
    kode: Annotated[str, Form(max_length=40)],
    db: DbSesjon,
    settings: AppSettings,
) -> Response:
    krev_ikke_sperret(db)
    if not passkeys.bruk_gjenopprettingskode(db, kode):
        registrer_feil(db, "kode")
        return templates.TemplateResponse(
            request,
            "logg_inn.html",
            {"har_passkeys": passkeys.finnes_passkeys(db), "kodefeil": True},
            status_code=400,
        )
    # Videre til oppsett, slik at en ny passkey kan registreres med en gang.
    svar = RedirectResponse("/oppsett", status_code=303)
    opprett_sesjon(db, svar, settings)
    return svar


@router.post("/logg-ut")
def logg_ut(request: Request, _: InnloggetMedCsrf, db: DbSesjon, settings: AppSettings) -> Response:
    svar = RedirectResponse("/logg-inn", status_code=303)
    avslutt_sesjon(db, request, svar, settings)
    return svar
