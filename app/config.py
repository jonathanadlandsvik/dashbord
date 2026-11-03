"""All konfigurasjon leses fra miljøvariabler (lokalt fra .env, i produksjon fra Vercel).

Ingen hemmeligheter står i koden. Verdier som først trengs i senere faser er valgfrie,
slik at appen kan starte før de er satt.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "production"] = "development"
    app_base_url: str = "http://localhost:8000"
    session_secret: SecretStr | None = None

    # Database (Neon) – tas i bruk i fase 2
    database_url: SecretStr | None = None
    database_url_unpooled: SecretStr | None = None

    # Vær og bysykkel – tas i bruk i fase 4
    yr_user_agent: str = "dashbord/2.0 github.com/jonathanadlandsvik/dashbord"
    vaer_lat: float = 63.4305
    vaer_lon: float = 10.3951
    bysykkel_stasjon_id: str = "293"

    @property
    def er_produksjon(self) -> bool:
        return self.app_env == "production"


@lru_cache
def hent_settings() -> Settings:
    return Settings()
