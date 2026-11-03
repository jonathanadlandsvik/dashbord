"""Sesjoner, CSRF og begrensning av innloggingsforsøk.

Sesjonen er et tilfeldig token i en HttpOnly-cookie. Databasen lagrer bare
SHA-256 av tokenet, så en lekket database gir ingen gyldige sesjoner, og en
sesjon kan avsluttes ved å slette raden.
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import Response
from sqlalchemy import delete, func
from sqlmodel import Session, select

from app.config import Settings
from app.db import hent_session
from app.models import Innloggingsforsok, Sesjon, Utfordring

SESJON_LEVETID = timedelta(days=90)  # logges ut etter 90 dager uten bruk
FORLENG_ETTER = timedelta(days=1)  # utløpstiden skyves frem maks én gang i døgnet
COOKIE_MAKS_ALDER = timedelta(days=400)  # nettlesernes øvre grense; databasen avgjør
MAKS_FEIL = 10
FEIL_VINDU = timedelta(minutes=15)


class IkkeInnlogget(Exception):
    """Fanges i main.py og blir til en videresending til innloggingssiden."""


class Ugyldig(Exception):
    """Avvist forespørsel. Meldingen vises for brukeren og skal ikke avsløre detaljer."""

    def __init__(self, melding: str, status_code: int = 400) -> None:
        super().__init__(melding)
        self.melding = melding
        self.status_code = status_code


def naa() -> datetime:
    return datetime.now(UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def nytt_token() -> str:
    return secrets.token_urlsafe(32)


def app_settings(request: Request) -> Settings:
    return request.app.state.settings


DbSesjon = Annotated[Session, Depends(hent_session)]
AppSettings = Annotated[Settings, Depends(app_settings)]


# ---------- Sesjoner ----------


def cookienavn(settings: Settings) -> str:
    # __Host- betyr at nettleseren bare godtar cookien over HTTPS, fra akkurat dette
    # domenet og for hele nettstedet. Lokalt kjører vi http, så der brukes et vanlig navn.
    return "__Host-sesjon" if settings.er_produksjon else "sesjon"


def opprett_sesjon(db: Session, svar: Response, settings: Settings) -> None:
    token = nytt_token()
    tid = naa()
    db.add(Sesjon(token_hash=hash_token(token), utloper=tid + SESJON_LEVETID, sist_sett=tid))
    db.commit()
    svar.set_cookie(
        cookienavn(settings),
        token,
        max_age=int(COOKIE_MAKS_ALDER.total_seconds()),
        httponly=True,
        secure=settings.er_produksjon,
        samesite="lax",
        path="/",
    )


def avslutt_sesjon(db: Session, request: Request, svar: Response, settings: Settings) -> None:
    if token := request.cookies.get(cookienavn(settings)):
        db.exec(delete(Sesjon).where(Sesjon.token_hash == hash_token(token)))
        db.commit()
    svar.delete_cookie(cookienavn(settings), path="/", secure=settings.er_produksjon)


def innlogget_sesjon(request: Request, db: Session, settings: Settings) -> Sesjon | None:
    token = request.cookies.get(cookienavn(settings))
    if not token:
        return None
    sesjon = db.get(Sesjon, hash_token(token))
    tid = naa()
    if sesjon is None or sesjon.utloper <= tid:
        return None
    if tid - sesjon.sist_sett > FORLENG_ETTER:
        sesjon.sist_sett = tid
        sesjon.utloper = tid + SESJON_LEVETID
        db.add(sesjon)
        db.commit()
    return sesjon


def krev_innlogging(request: Request, db: DbSesjon, settings: AppSettings) -> Sesjon:
    sesjon = innlogget_sesjon(request, db, settings)
    if sesjon is None:
        raise IkkeInnlogget
    request.state.sesjon = sesjon
    return sesjon


Innlogget = Annotated[Sesjon, Depends(krev_innlogging)]


# ---------- CSRF ----------
# Tokenet er en HMAC av sesjonen, så det trenger ikke lagres. En angriper på et
# annet nettsted kan ikke lese det, og dermed ikke lage en gyldig forespørsel.


def csrf_token(request: Request, sesjon: Sesjon) -> str:
    nokkel: bytes = request.app.state.csrf_nokkel
    return hmac.new(nokkel, sesjon.token_hash.encode(), hashlib.sha256).hexdigest()


async def krev_csrf(request: Request, sesjon: Innlogget) -> Sesjon:
    oppgitt = request.headers.get("x-csrf-token")
    if oppgitt is None and request.headers.get("content-type", "").startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        oppgitt = (await request.form()).get("csrf_token")
    if not isinstance(oppgitt, str) or not hmac.compare_digest(
        oppgitt, csrf_token(request, sesjon)
    ):
        raise Ugyldig("Siden er utdatert. Last den inn på nytt og prøv igjen.", 403)
    return sesjon


InnloggetMedCsrf = Annotated[Sesjon, Depends(krev_csrf)]


# ---------- Utfordringer (WebAuthn-challenges) ----------

UTFORDRING_LEVETID = timedelta(minutes=5)


def lagre_utfordring(db: Session, challenge: bytes, formal: str) -> str:
    token = nytt_token()
    db.add(
        Utfordring(
            token_hash=hash_token(token),
            challenge=challenge,
            formal=formal,
            utloper=naa() + UTFORDRING_LEVETID,
        )
    )
    db.commit()
    return token


def bruk_utfordring(db: Session, token: str, formal: str) -> bytes:
    """Henter og sletter challengen. Den kan bare brukes én gang."""
    utfordring = db.get(Utfordring, hash_token(token))
    if utfordring is None:
        raise Ugyldig("Forsøket er utløpt. Prøv igjen.")
    db.delete(utfordring)
    db.commit()
    if utfordring.formal != formal or utfordring.utloper <= naa():
        raise Ugyldig("Forsøket er utløpt. Prøv igjen.")
    return utfordring.challenge


# ---------- Begrensning av forsøk ----------


def krev_ikke_sperret(db: Session) -> None:
    grense = naa() - FEIL_VINDU
    antall = db.exec(
        select(func.count())
        .select_from(Innloggingsforsok)
        .where(Innloggingsforsok.tidspunkt > grense)
    ).one()
    if antall >= MAKS_FEIL:
        raise Ugyldig("For mange mislykkede forsøk. Vent et kvarter og prøv igjen.", 429)


def registrer_feil(db: Session, metode: str) -> None:
    db.add(Innloggingsforsok(metode=metode))
    db.commit()


def rydd_opp(db: Session) -> None:
    """Fjerner utløpte rader, så tabellene ikke vokser for alltid."""
    tid = naa()
    db.exec(delete(Utfordring).where(Utfordring.utloper <= tid))
    db.exec(delete(Sesjon).where(Sesjon.utloper <= tid))
    db.exec(delete(Innloggingsforsok).where(Innloggingsforsok.tidspunkt <= tid - timedelta(days=1)))
    db.commit()
