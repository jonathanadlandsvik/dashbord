"""
Mottaker for helsedata fra iPhone (Snarveier) – kjører på PythonAnywhere.

Endepunkter:
    POST /helsedata          – iPhone sender gårsdagens tall. Krever SKRIVENØKKEL.
    GET  /helsedata/<dato>   – Dashbordet henter tallene for en dag. Krever LESENØKKEL.

Sikkerhet:
    - To separate nøkler (minste privilegium): nøkkelen som ligger på telefonen kan bare
      skrive, nøkkelen som ligger i Streamlit kan bare lese.
    - Nøklene leses fra miljøvariabler (satt fra .env i wsgi.py), aldri fra koden.
    - Nøkler sammenlignes med hmac.compare_digest for å unngå timing-angrep.
    - All input valideres (format, type og fornuftige verdiområder) og størrelsen på
      forespørselen er begrenset.
    - SQL-spørringene bruker parametre (?), som hindrer SQL-injeksjon.
"""
import hmac
import math
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024  # 10 kB er mer enn nok for fire tall

# Absolutt sti, slik at databasen havner samme sted uansett hvilken mappe appen startes fra
DATABASE = Path(__file__).resolve().parent / "helsedata.db"

# Feltnavn -> (minste, største) tillatte verdi
FELT = {
    "skritt": (0, 200_000),
    "aktiv_energi": (0, 20_000),      # kcal
    "treningsminutter": (0, 1_440),
    "oppreist_timer": (0, 24),
}


# ---------- Database ----------

def koble_til():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dagsaktivitet (
            dato TEXT PRIMARY KEY,
            skritt REAL,
            aktiv_energi REAL,
            treningsminutter REAL,
            oppreist_timer REAL,
            mottatt TEXT NOT NULL
        )
    """)
    return conn


# ---------- Autentisering ----------

def har_gyldig_nokkel(miljovariabel):
    forventet = os.environ.get(miljovariabel)
    if not forventet:
        # "Fail closed": mangler nøkkelen på serveren, slipper ingen inn.
        app.logger.error("Miljøvariabelen %s er ikke satt", miljovariabel)
        return False

    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    oppgitt = header.removeprefix("Bearer ").strip()
    return hmac.compare_digest(oppgitt.encode(), forventet.encode())


def ikke_autorisert():
    return jsonify({"feil": "ugyldig eller manglende API-nøkkel"}), 401, {"WWW-Authenticate": "Bearer"}


# ---------- Validering ----------

def tolk_tall(verdi):
    """Godtar tall, eller tekst med komma/punktum som desimaltegn (Snarveier kan sende begge)."""
    if isinstance(verdi, bool):
        raise ValueError("må være et tall")
    if isinstance(verdi, (int, float)):
        tall = float(verdi)
    elif isinstance(verdi, str):
        tall = float(verdi.strip().replace(" ", "").replace(" ", "").replace(",", "."))
    else:
        raise ValueError("må være et tall")
    if not math.isfinite(tall):
        raise ValueError("må være et endelig tall")
    return tall


def valider(data):
    """Returnerer (rensede data, None) eller (None, feilmelding)."""
    if not isinstance(data, dict):
        return None, "forventet et JSON-objekt"

    ukjente = set(data) - set(FELT) - {"dato"}
    if ukjente:
        return None, f"ukjente felt: {', '.join(sorted(ukjente))}"

    try:
        dato = date.fromisoformat(str(data.get("dato", "")))
    except ValueError:
        return None, "dato må være på formatet ÅÅÅÅ-MM-DD"
    if dato > date.today() + timedelta(days=1):
        return None, "dato kan ikke være i fremtiden"

    renset = {"dato": dato.isoformat()}
    for navn, (minst, maks) in FELT.items():
        if data.get(navn) in (None, ""):
            renset[navn] = None  # feltet er valgfritt
            continue
        try:
            tall = tolk_tall(data[navn])
        except ValueError as feil:
            return None, f"{navn} {feil}"
        if not minst <= tall <= maks:
            return None, f"{navn} må være mellom {minst} og {maks}"
        renset[navn] = tall

    return renset, None


# ---------- Endepunkter ----------

@app.post("/helsedata")
def motta_helsedata():
    if not har_gyldig_nokkel("HELSE_SKRIVENOKKEL"):
        return ikke_autorisert()

    data, feil = valider(request.get_json(silent=True))
    if feil:
        return jsonify({"feil": feil}), 400

    with koble_til() as conn:
        # Én rad per dag: sender telefonen samme dag to ganger, blir raden oppdatert.
        conn.execute("""
            INSERT INTO dagsaktivitet (dato, skritt, aktiv_energi, treningsminutter, oppreist_timer, mottatt)
            VALUES (:dato, :skritt, :aktiv_energi, :treningsminutter, :oppreist_timer, :mottatt)
            ON CONFLICT(dato) DO UPDATE SET
                skritt = excluded.skritt,
                aktiv_energi = excluded.aktiv_energi,
                treningsminutter = excluded.treningsminutter,
                oppreist_timer = excluded.oppreist_timer,
                mottatt = excluded.mottatt
        """, {**data, "mottatt": datetime.now(timezone.utc).isoformat()})
    conn.close()

    return jsonify({"status": "lagret", "dato": data["dato"]}), 200


@app.get("/helsedata/<dato>")
def hent_helsedata(dato):
    if not har_gyldig_nokkel("HELSE_LESENOKKEL"):
        return ikke_autorisert()

    try:
        dato = date.fromisoformat(dato).isoformat()
    except ValueError:
        return jsonify({"feil": "dato må være på formatet ÅÅÅÅ-MM-DD"}), 400

    with koble_til() as conn:
        rad = conn.execute("SELECT * FROM dagsaktivitet WHERE dato = ?", (dato,)).fetchone()
    conn.close()

    if rad is None:
        return jsonify({"feil": "ingen data for denne datoen"}), 404
    return jsonify(dict(rad)), 200


@app.errorhandler(413)
def for_stor(_):
    return jsonify({"feil": "forespørselen er for stor"}), 413
