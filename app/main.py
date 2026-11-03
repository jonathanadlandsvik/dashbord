"""Inngangspunktet. Vercel laster `app` herfra (se [tool.vercel] i pyproject.toml)."""

import logging
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlmodel import Session

from app.auth import IkkeInnlogget, Ugyldig
from app.config import Settings, hent_settings
from app.db import hent_session
from app.routers import api, bokser, forside, innlogging
from app.sikkerhet import Sikkerhetsmiddleware

logger = logging.getLogger(__name__)

PUBLIC = Path(__file__).resolve().parent.parent / "public"


def lag_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="Hverdagsdashbord",
        # API-dokumentasjonen er nyttig lokalt, men skal ikke ligge åpen i produksjon.
        docs_url=None if settings.er_produksjon else "/docs",
        redoc_url=None,
        openapi_url=None if settings.er_produksjon else "/openapi.json",
    )
    app.state.settings = settings
    # Nøkkelen for CSRF-tokenene. Lokalt uten SESSION_SECRET lages en tilfeldig en
    # ved oppstart (da blir du logget ut av skjemaene når serveren starter på nytt).
    app.state.csrf_nokkel = (
        settings.session_secret.get_secret_value().encode()
        if settings.session_secret
        else secrets.token_bytes(32)
    )

    app.add_middleware(
        Sikkerhetsmiddleware, origin=settings.origin, produksjon=settings.er_produksjon
    )

    @app.exception_handler(IkkeInnlogget)
    def til_innlogging(request: Request, _: IkkeInnlogget) -> Response:
        if request.headers.get("hx-request"):
            # HTMX følger ikke vanlige videresendinger for hele siden, men denne headeren.
            return Response(status_code=401, headers={"HX-Redirect": "/logg-inn"})
        if "text/html" in request.headers.get("accept", "") or request.method == "GET":
            return RedirectResponse("/logg-inn", status_code=303)
        return JSONResponse({"feil": "Ikke innlogget."}, status_code=401)

    @app.exception_handler(Ugyldig)
    def avvist(_: Request, feil: Ugyldig) -> JSONResponse:
        return JSONResponse({"feil": feil.melding}, status_code=feil.status_code)

    # På Vercel serveres public/ fra CDN-et, og mappa er ikke med i selve funksjonen.
    # Lokalt finnes den, og da serverer FastAPI filene selv.
    statisk = PUBLIC / "static"
    if statisk.is_dir():
        app.mount("/static", StaticFiles(directory=statisk), name="static")

    app.include_router(innlogging.router)
    app.include_router(forside.router)
    app.include_router(bokser.router)
    app.include_router(api.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/healthz/db", include_in_schema=False)
    def healthz_db(session: Annotated[Session, Depends(hent_session)]) -> JSONResponse:
        try:
            session.exec(text("SELECT 1"))
        except Exception:
            # Detaljene havner i loggen hos Vercel, aldri i svaret til nettleseren.
            logger.exception("Databasesjekken feilet")
            return JSONResponse({"database": "utilgjengelig"}, status_code=503)
        return JSONResponse({"database": "ok"})

    return app


app = lag_app(hent_settings())
