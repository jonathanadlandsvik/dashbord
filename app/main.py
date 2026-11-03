"""Inngangspunktet. Vercel laster `app` herfra (se [tool.vercel] i pyproject.toml)."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlmodel import Session

from app.config import Settings, hent_settings
from app.db import hent_session
from app.routers import forside

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

    # På Vercel serveres public/ fra CDN-et, og mappa er ikke med i selve funksjonen.
    # Lokalt finnes den, og da serverer FastAPI filene selv.
    statisk = PUBLIC / "static"
    if statisk.is_dir():
        app.mount("/static", StaticFiles(directory=statisk), name="static")

    app.include_router(forside.router)

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
