"""
Henter et nytt Google OAuth-token for kalenderen og lagrer det i .streamlit/secrets.toml.

Kjør lokalt (med venv aktivert):
    python hent_token.py

Scriptet åpner nettleseren, du logger inn med Google-kontoen din og godkjenner
lesetilgang til kalenderen. Deretter skrives refresh_token, client_id og
client_secret til .streamlit/secrets.toml (som er gitignored).
Innholdet i den filen må også limes inn under "Secrets" i Streamlit Cloud.
"""
import json
import tomllib
from pathlib import Path

import toml
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CREDENTIALS_FIL = Path("credentials.json")
SECRETS_FIL = Path(".streamlit/secrets.toml")


def main():
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FIL, SCOPES)
    # access_type="offline" gir refresh_token, prompt="consent" tvinger Google
    # til å utstede et nytt et selv om du har godkjent appen før.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    if not creds.refresh_token:
        raise SystemExit("Fikk ikke refresh_token fra Google – prøv igjen.")

    klient = json.loads(CREDENTIALS_FIL.read_text())["installed"]

    secrets = tomllib.loads(SECRETS_FIL.read_text()) if SECRETS_FIL.exists() else {}
    secrets["google"] = {
        "refresh_token": creds.refresh_token,
        "client_id": klient["client_id"],
        "client_secret": klient["client_secret"],
    }

    SECRETS_FIL.parent.mkdir(exist_ok=True)
    SECRETS_FIL.write_text(toml.dumps(secrets))
    print(f"Nytt token lagret i {SECRETS_FIL}. Husk å oppdatere Secrets i Streamlit Cloud også.")


if __name__ == "__main__":
    main()
