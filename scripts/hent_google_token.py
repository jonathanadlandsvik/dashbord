"""Henter et nytt refresh token for Google Calendar og skriver det til .env.

Trengs hvis kalenderboksen sier at Google-tilgangen er utløpt. Kjør lokalt:

    uv run --with google-auth-oauthlib python scripts/hent_google_token.py

Krever credentials.json fra Google Cloud Console (OAuth-klient av typen
«Desktop app») i prosjektmappa. Den er i .gitignore. Nettleseren åpnes, du
godkjenner lesetilgang til kalenderen, og GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
og GOOGLE_REFRESH_TOKEN oppdateres i .env. Ingen verdier skrives ut.

Biblioteket installeres bare for denne ene kjøringen (--with), så appen selv
slipper avhengigheten.
"""

import json
import re
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]  # bare lesetilgang
CREDENTIALS = Path("credentials.json")
ENV = Path(".env")


def oppdater_env(verdier: dict[str, str]) -> None:
    linjer = ENV.read_text().splitlines() if ENV.exists() else []
    gjenstar = dict(verdier)
    ut = []
    for linje in linjer:
        treff = re.match(r"^([A-Z_]+)=", linje)
        if treff and treff[1] in gjenstar:
            linje = f"{treff[1]}={gjenstar.pop(treff[1])}"
        ut.append(linje)
    ut += [f"{nokkel}={verdi}" for nokkel, verdi in gjenstar.items()]
    ENV.write_text("\n".join(ut) + "\n")


def main() -> None:
    if not CREDENTIALS.exists():
        sys.exit("Fant ikke credentials.json. Last den ned fra Google Cloud Console.")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS, SCOPES)
    # access_type=offline gir refresh token; prompt=consent tvinger frem et nytt.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        sys.exit("Google ga ikke noe refresh token. Prøv igjen.")
    klient = json.loads(CREDENTIALS.read_text())
    klient = klient.get("installed") or klient.get("web") or {}
    oppdater_env(
        {
            "GOOGLE_CLIENT_ID": klient["client_id"],
            "GOOGLE_CLIENT_SECRET": klient["client_secret"],
            "GOOGLE_REFRESH_TOKEN": creds.refresh_token,
        }
    )
    print("Oppdaterte .env. Legg den nye GOOGLE_REFRESH_TOKEN inn i Vercel også:")
    print("  grep '^GOOGLE_REFRESH_TOKEN=' .env | cut -d= -f2- | tr -d '\\n' | pbcopy")


if __name__ == "__main__":
    main()
