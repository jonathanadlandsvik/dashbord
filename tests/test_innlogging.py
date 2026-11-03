"""Innlogging, oppsett og sesjoner, testet mot en ekte Postgres.

Selve signatursjekken i py_webauthn krever en ekte autentikator (Face ID), så den
erstattes her med en kontrollert versjon. Alt rundt den kjører som i produksjon.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select
from webauthn.helpers import bytes_to_base64url

import app.passkeys
from app.auth import MAKS_FEIL, hash_token, naa
from app.db import hent_session
from app.main import lag_app
from app.models import Gjenopprettingskode, Innloggingsforsok, Passkey, Sesjon, Utfordring
from tests.conftest import lag_testklient, settings_for

SETUP = "riktig-oppsettkode"
PASSKEY_ID = b"min-iphone"


@pytest.fixture
def lag_klient(session: Session):
    def lag(**settings):
        app_ = lag_app(settings_for(**({"setup_token": SETUP} | settings)))
        app_.dependency_overrides[hent_session] = lambda: session
        return lag_testklient(app_, https=settings.get("app_env") == "production")

    return lag


@pytest.fixture
def klient_db(lag_klient):
    return lag_klient()


@pytest.fixture(autouse=True)
def falsk_autentikator(monkeypatch):
    """Later som Face ID godkjente. Teller kall, så testene kan se at sjekken faktisk ble gjort."""
    kall = {"registrering": 0, "innlogging": 0}

    def registrering(**kwargs):
        kall["registrering"] += 1
        assert kwargs["require_user_verification"] is True
        return SimpleNamespace(credential_id=PASSKEY_ID, credential_public_key=b"pk", sign_count=0)

    def innlogging(**kwargs):
        kall["innlogging"] += 1
        assert kwargs["require_user_verification"] is True
        return SimpleNamespace(new_sign_count=kwargs["credential_current_sign_count"] + 1)

    monkeypatch.setattr(app.passkeys, "verify_registration_response", registrering)
    monkeypatch.setattr(app.passkeys, "verify_authentication_response", innlogging)
    return kall


def credential(passkey_id: bytes = PASSKEY_ID) -> dict:
    return {"id": bytes_to_base64url(passkey_id), "rawId": bytes_to_base64url(passkey_id)}


def registrer_forste(klient) -> dict:
    start = klient.post("/auth/registrering/start", json={"setup_token": SETUP})
    assert start.status_code == 200, start.text
    svar = klient.post(
        "/auth/registrering/fullfor",
        json={
            "utfordring": start.json()["utfordring"],
            "credential": credential(),
            "navn": "iPhone",
            "setup_token": SETUP,
        },
    )
    assert svar.status_code == 200, svar.text
    return svar.json()


def logg_inn(klient):
    start = klient.post("/auth/innlogging/start")
    assert start.status_code == 200, start.text
    return klient.post(
        "/auth/innlogging/fullfor",
        json={"utfordring": start.json()["utfordring"], "credential": credential()},
    )


def csrf_fra(klient) -> str:
    side = klient.get("/").text
    return side.split('name="csrf-token" content="')[1].split('"')[0]


# ---------- Uten innlogging ----------


def test_forsiden_krever_innlogging(klient_db):
    svar = klient_db.get("/", follow_redirects=False)
    assert svar.status_code == 303
    assert svar.headers["location"] == "/logg-inn"


def test_htmx_forespørsel_far_hx_redirect(klient_db):
    svar = klient_db.get("/", headers={"HX-Request": "true"})
    assert svar.status_code == 401
    assert svar.headers["hx-redirect"] == "/logg-inn"


def test_innloggingssiden_viser_oppsett_forste_gang(klient_db):
    side = klient_db.get("/logg-inn").text
    assert "Sett opp innlogging" in side
    assert "gjenopprettingskode" not in side.lower()


# ---------- Første oppsett ----------


@pytest.mark.parametrize("token", [None, "", "feil-kode", SETUP + "x"])
def test_forste_registrering_krever_riktig_oppsettkode(klient_db, session, token):
    svar = klient_db.post("/auth/registrering/start", json={"setup_token": token})
    assert svar.status_code == 403
    assert session.exec(select(Innloggingsforsok)).all()  # forsøket er registrert


def test_uten_setup_token_i_miljoet_kan_ingen_registrere(lag_klient):
    klient = lag_klient(setup_token=None)
    assert klient.post("/auth/registrering/start", json={"setup_token": ""}).status_code == 403


def test_forste_registrering_gir_koder_og_innlogging(klient_db, session, falsk_autentikator):
    data = registrer_forste(klient_db)
    assert len(data["koder"]) == 10
    assert len(set(data["koder"])) == 10
    assert falsk_autentikator["registrering"] == 1
    assert session.get(Passkey, PASSKEY_ID).navn == "iPhone"
    assert klient_db.get("/", follow_redirects=False).status_code == 200


def test_kodene_lagres_bare_som_hash(klient_db, session):
    koder = registrer_forste(klient_db)["koder"]
    lagret = {k.kode_hash for k in session.exec(select(Gjenopprettingskode)).all()}
    assert not any(kode in h or kode.replace("-", "") in h for kode in koder for h in lagret)
    assert hash_token(koder[0].replace("-", "")) in lagret


def test_oppsettkoden_virker_ikke_nar_en_passkey_finnes(lag_klient):
    forste = lag_klient()
    registrer_forste(forste)
    fremmed = lag_klient()  # ny nettleser uten sesjon, men med den lekkede koden
    svar = fremmed.post("/auth/registrering/start", json={"setup_token": SETUP})
    assert svar.status_code == 403


def test_innlogget_kan_legge_til_passkey_bare_med_csrf(klient_db):
    registrer_forste(klient_db)
    uten = klient_db.post("/auth/registrering/start", json={})
    assert uten.status_code == 403
    med = klient_db.post(
        "/auth/registrering/start", json={}, headers={"X-CSRF-Token": csrf_fra(klient_db)}
    )
    assert med.status_code == 200


# ---------- Innlogging ----------


def test_innlogging_med_passkey(lag_klient, session, falsk_autentikator):
    registrer_forste(lag_klient())
    ny = lag_klient()
    svar = logg_inn(ny)
    assert svar.status_code == 200
    assert falsk_autentikator["innlogging"] == 1
    passkey = session.get(Passkey, PASSKEY_ID)
    assert passkey.signaturteller == 1
    assert passkey.sist_brukt is not None
    assert ny.get("/", follow_redirects=False).status_code == 200


def test_sesjonstokenet_lagres_bare_som_hash(lag_klient, session):
    registrer_forste(lag_klient())
    ny = lag_klient()
    logg_inn(ny)
    token = ny.cookies["sesjon"]
    lagret = [s.token_hash for s in session.exec(select(Sesjon)).all()]
    assert token not in lagret
    assert hash_token(token) in lagret


def test_utfordring_kan_bare_brukes_en_gang(lag_klient):
    registrer_forste(lag_klient())
    ny = lag_klient()
    utfordring = ny.post("/auth/innlogging/start").json()["utfordring"]
    data = {"utfordring": utfordring, "credential": credential()}
    assert ny.post("/auth/innlogging/fullfor", json=data).status_code == 200
    assert ny.post("/auth/innlogging/fullfor", json=data).status_code == 400


def test_utlopt_utfordring_avvises(lag_klient, session):
    registrer_forste(lag_klient())
    ny = lag_klient()
    utfordring = ny.post("/auth/innlogging/start").json()["utfordring"]
    rad = session.get(Utfordring, hash_token(utfordring))
    rad.utloper = naa() - timedelta(seconds=1)
    session.add(rad)
    session.flush()
    svar = ny.post(
        "/auth/innlogging/fullfor", json={"utfordring": utfordring, "credential": credential()}
    )
    assert svar.status_code == 400


def test_registreringsutfordring_kan_ikke_brukes_til_innlogging(klient_db):
    registrer_forste(klient_db)
    start = klient_db.post(
        "/auth/registrering/start", json={}, headers={"X-CSRF-Token": csrf_fra(klient_db)}
    )
    svar = klient_db.post(
        "/auth/innlogging/fullfor",
        json={"utfordring": start.json()["utfordring"], "credential": credential()},
    )
    assert svar.status_code == 400


def test_ukjent_passkey_avvises_og_telles(lag_klient, session):
    registrer_forste(lag_klient())
    ny = lag_klient()
    utfordring = ny.post("/auth/innlogging/start").json()["utfordring"]
    svar = ny.post(
        "/auth/innlogging/fullfor",
        json={"utfordring": utfordring, "credential": credential(b"en-annen-enhet")},
    )
    assert svar.status_code == 400
    assert "sesjon" not in ny.cookies
    assert session.exec(select(Innloggingsforsok)).all()


def test_sperres_etter_for_mange_feil(lag_klient, session):
    registrer_forste(lag_klient())
    for _ in range(MAKS_FEIL):
        session.add(Innloggingsforsok(metode="passkey"))
    session.flush()
    assert lag_klient().post("/auth/innlogging/start").status_code == 429


# ---------- Gjenopprettingskoder ----------


def test_gjenopprettingskode_virker_en_gang(lag_klient):
    kode = registrer_forste(lag_klient())["koder"][0]
    ny = lag_klient()
    svar = ny.post("/logg-inn/kode", data={"kode": kode.lower()}, follow_redirects=False)
    assert svar.status_code == 303
    assert svar.headers["location"] == "/oppsett"
    assert ny.get("/", follow_redirects=False).status_code == 200

    igjen = lag_klient().post("/logg-inn/kode", data={"kode": kode})
    assert igjen.status_code == 400
    assert "ugyldig eller allerede brukt" in igjen.text


# ---------- Sesjoner og utlogging ----------


def test_utlogging_krever_csrf_og_sletter_sesjonen(klient_db, session):
    registrer_forste(klient_db)
    assert klient_db.post("/logg-ut").status_code == 403
    svar = klient_db.post(
        "/logg-ut", data={"csrf_token": csrf_fra(klient_db)}, follow_redirects=False
    )
    assert svar.status_code == 303
    assert session.exec(select(Sesjon)).all() == []
    assert klient_db.get("/", follow_redirects=False).status_code == 303


def test_utlopt_sesjon_gir_ny_innlogging(klient_db, session):
    registrer_forste(klient_db)
    sesjon = session.exec(select(Sesjon)).one()
    sesjon.utloper = naa() - timedelta(minutes=1)
    session.add(sesjon)
    session.flush()
    assert klient_db.get("/", follow_redirects=False).status_code == 303


def test_sesjonscookie_i_utvikling(klient_db):
    registrer_forste(klient_db)
    cookie = next(c for c in klient_db.cookies.jar if c.name == "sesjon")
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert not cookie.secure


def test_sesjonscookie_i_produksjon(lag_klient):
    klient = lag_klient(app_env="production")
    registrer_forste(klient)
    cookie = next(c for c in klient.cookies.jar if c.name == "__Host-sesjon")
    assert cookie.secure
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert cookie.path == "/"
    assert not cookie.domain_specified
