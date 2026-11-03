"""All konfigurasjon leses fra miljøvariabler (lokalt fra .env, i produksjon fra Vercel).

Ingen hemmeligheter står i koden. Verdier som først trengs i senere faser er valgfrie,
slik at appen kan starte før de er satt.
"""

from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "production"] = "development"
    app_base_url: str = "http://localhost:8000"  # uten skråstrek til slutt
    session_secret: SecretStr | None = None

    # Engangstoken for å registrere den første passkeyen. Slettes etterpå.
    setup_token: SecretStr | None = None

    # Database (Neon) – tas i bruk i fase 2
    database_url: SecretStr | None = None
    database_url_unpooled: SecretStr | None = None

    # Vær og bysykkel – tas i bruk i fase 4
    yr_user_agent: str = "dashbord/2.0 github.com/jonathanadlandsvik/dashbord"
    vaer_lat: float = 63.4305
    vaer_lon: float = 10.3951
    bysykkel_stasjon_id: str = "293"

    # Google Calendar (samme OAuth-klient og refresh token som i v1)
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_refresh_token: SecretStr | None = None

    @property
    def er_produksjon(self) -> bool:
        return self.app_env == "production"

    @property
    def origin(self) -> str:
        """For eksempel https://dashbord-xyz.vercel.app. Passkeys og Origin-sjekken bruker den."""
        return self.app_base_url.rstrip("/")

    @property
    def rp_id(self) -> str:
        """Domenet passkeyen knyttes til, uten https:// og port."""
        return urlsplit(self.origin).hostname or "localhost"

    @model_validator(mode="after")
    def krav_i_produksjon(self) -> Self:
        # "Fail closed": mangler noe viktig i produksjon, starter ikke appen i det hele tatt.
        if self.er_produksjon:
            if not self.origin.startswith("https://"):
                raise ValueError("APP_BASE_URL må starte med https:// i produksjon")
            hemmelig = self.session_secret.get_secret_value() if self.session_secret else ""
            if len(hemmelig) < 32:
                raise ValueError("SESSION_SECRET må være satt og minst 32 tegn i produksjon")
        return self


@lru_cache
def hent_settings() -> Settings:
    return Settings()
