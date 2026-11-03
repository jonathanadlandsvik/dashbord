"""Tilkobling til Postgres (Neon).

Appen bruker den pooled adressen (DATABASE_URL). Migrasjoner bruker den direkte
(DATABASE_URL_UNPOOLED), se migrations/env.py.
"""

from collections.abc import Iterator

from fastapi import FastAPI, Request
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

# Neons pooler (PgBouncer) deler tilkoblinger mellom klienter. Da må psycopg ikke
# lage navngitte prepared statements, som hører til én bestemt tilkobling.
PSYCOPG_ARGS = {"prepare_threshold": None}


def til_sqlalchemy_url(url: str) -> str:
    """Neon gir postgresql://..., men SQLAlchemy må få vite at driveren er psycopg 3."""
    for prefiks in ("postgresql://", "postgres://"):
        if url.startswith(prefiks):
            return "postgresql+psycopg://" + url.removeprefix(prefiks)
    return url


def lag_engine(url: str) -> Engine:
    return create_engine(
        til_sqlalchemy_url(url),
        pool_pre_ping=True,  # oppdager tilkoblinger Neon har lukket mens funksjonen sov
        pool_recycle=300,
        pool_size=2,
        max_overflow=3,
        connect_args=PSYCOPG_ARGS,
    )


def hent_engine(app: FastAPI) -> Engine:
    """Én engine per app, laget første gang den trengs, fra appens egne innstillinger.

    Ikke fra en global konfigurasjon: da kunne testene (eller en app med andre
    innstillinger) ende opp med å koble seg til databasen i .env.
    """
    engine = getattr(app.state, "engine", None)
    if engine is None:
        settings = app.state.settings
        if settings.database_url is None:
            raise RuntimeError("DATABASE_URL er ikke satt")
        engine = app.state.engine = lag_engine(settings.database_url.get_secret_value())
    return engine


def hent_session(request: Request) -> Iterator[Session]:
    """FastAPI-avhengighet: én databasesesjon per forespørsel."""
    with Session(hent_engine(request.app)) as session:
        yield session
