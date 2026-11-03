import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import lag_app


def settings_for(**verdier) -> Settings:
    # _env_file=None: testene skal aldri lese den ekte .env-filen
    return Settings(_env_file=None, **verdier)


@pytest.fixture
def klient() -> TestClient:
    return TestClient(lag_app(settings_for(app_env="development")))


@pytest.fixture
def prod_klient() -> TestClient:
    return TestClient(lag_app(settings_for(app_env="production")))
