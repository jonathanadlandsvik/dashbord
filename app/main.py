"""Inngangspunktet. Vercel laster `app` herfra (se [tool.vercel] i pyproject.toml)."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import Settings, hent_settings
from app.routers import forside

PUBLIC = Path(__file__).resolve().parent.parent / "public"


def lag_app(settings: Settings) -> FastAPI:
    app = FastAPI(
        title="Hverdagsdashbord",
        # API-dokumentasjonen er nyttig lokalt, men skal ikke ligge åpen i produksjon.
        docs_url=None if settings.er_produksjon else "/docs",
        redoc_url=None,
        openapi_url=None if settings.er_produksjon else "/openapi.json",
    )

    # På Vercel serveres public/ direkte fra CDN-et. Lokalt gjør FastAPI det samme.
    app.mount("/static", StaticFiles(directory=PUBLIC / "static"), name="static")

    app.include_router(forside.router)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = lag_app(hent_settings())
