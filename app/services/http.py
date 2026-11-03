"""Felles innstillinger for kall mot eksterne tjenester."""

import httpx

# Kort timeout: én treg tjeneste skal ikke holde igjen resten av forsiden.
TIMEOUT = httpx.Timeout(4.0, connect=3.0)


def user_agent(settings) -> str:
    # MET krever en User-Agent som identifiserer appen og hvordan man når eieren.
    return settings.yr_user_agent
