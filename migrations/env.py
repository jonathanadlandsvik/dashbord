"""Kjøres av Alembic. Kobler til med den DIREKTE adressen (uten -pooler).

Neons pooler kjører i transaksjonsmodus, og der kan migrasjoner feile på måter
som er vanskelige å feilsøke. Derfor brukes DATABASE_URL_UNPOOLED her.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registrerer tabellene i SQLModel.metadata)
from app.config import hent_settings
from app.db import PSYCOPG_ARGS, til_sqlalchemy_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def database_url() -> str:
    # Testene sender inn adressen direkte. Ellers brukes miljøvariabelen.
    if url := config.attributes.get("url"):
        return til_sqlalchemy_url(url)
    settings = hent_settings()
    if settings.database_url_unpooled is None:
        raise SystemExit(
            "DATABASE_URL_UNPOOLED er ikke satt. Legg den i .env, eller sett den foran "
            "kommandoen. Bruk den direkte adressen fra Neon, uten -pooler."
        )
    return til_sqlalchemy_url(settings.database_url_unpooled.get_secret_value())


def kjor_migrasjoner() -> None:
    engine = create_engine(database_url(), poolclass=pool.NullPool, connect_args=PSYCOPG_ARGS)
    with engine.connect() as tilkobling:
        context.configure(connection=tilkobling, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline-modus brukes ikke i dette prosjektet.")
kjor_migrasjoner()
