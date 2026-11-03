import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, pool
from sqlmodel import Session, create_engine

from app.config import Settings
from app.db import PSYCOPG_ARGS, til_sqlalchemy_url
from app.main import lag_app

HEMMELIG = "t" * 40


def settings_for(**verdier) -> Settings:
    # _env_file=None: testene skal aldri lese den ekte .env-filen
    standard = {"app_base_url": "http://testserver"}
    if verdier.get("app_env") == "production":
        standard = {"app_base_url": "https://testserver", "session_secret": HEMMELIG}
    return Settings(_env_file=None, **(standard | verdier))


def lag_testklient(app, *, https: bool = False) -> TestClient:
    base = "https://testserver" if https else "http://testserver"
    # Nettleseren sender Origin på POST. Testklienten må gjøre det samme.
    return TestClient(app, base_url=base, headers={"Origin": base})


@pytest.fixture
def klient() -> TestClient:
    return lag_testklient(lag_app(settings_for(app_env="development")))


@pytest.fixture
def prod_klient() -> TestClient:
    return lag_testklient(lag_app(settings_for(app_env="production")), https=True)


# ---------- Database ----------
# Databasetestene kjører bare når TEST_DATABASE_URL er satt. I GitHub Actions
# peker den på en egen Postgres-container. Pek den ALDRI på Neon: testene
# sletter og lager tabellene på nytt.


def alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.attributes["url"] = url
    return config


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL er ikke satt")
    return url


@pytest.fixture(scope="session")
def migrert_engine(test_db_url) -> Iterator[Engine]:
    config = alembic_config(test_db_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(
        til_sqlalchemy_url(test_db_url), poolclass=pool.NullPool, connect_args=PSYCOPG_ARGS
    )
    yield engine
    engine.dispose()


@pytest.fixture
def session(migrert_engine) -> Iterator[Session]:
    """Hver test kjører i en transaksjon som rulles tilbake, så testene ikke påvirker hverandre."""
    with migrert_engine.connect() as tilkobling:
        transaksjon = tilkobling.begin()
        with Session(bind=tilkobling, join_transaction_mode="create_savepoint") as s:
            yield s
        transaksjon.rollback()
