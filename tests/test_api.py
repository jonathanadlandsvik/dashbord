"""Mottak av helsedata fra iPhone-snarveien, nøkler og import fra v1."""

import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import verktoy
from app.auth import SESJON_LEVETID, hash_token, naa
from app.db import hent_session
from app.helsedata import tolk_tall
from app.main import lag_app
from app.models import Dagsmaling, IngestNokkel, Sesjon
from tests.conftest import lag_testklient, settings_for

GYLDIG = {
    "dato": "2026-11-02",
    "skritt": "8 123",
    "aktiv_energi": "412,5",
    "treningsminutter": 35,
    "staatimer": "10",
}


@pytest.fixture
def api(session: Session):
    app_ = lag_app(settings_for())
    app_.dependency_overrides[hent_session] = lambda: session
    # Uten Origin-header, slik snarveien sender. /api/ skal ikke kreve den.
    return TestClient(app_)


@pytest.fixture
def nokkel(session: Session) -> str:
    return verktoy.ny_nokkel(session, "iPhone")


def malinger(session: Session) -> dict[str, float]:
    return {r.maling: r.verdi for r in session.exec(select(Dagsmaling)).all()}


# ---------- Tall fra Snarveier ----------


@pytest.mark.parametrize(
    ("inn", "ut"),
    [
        (5, 5.0),
        (2.5, 2.5),
        ("412,5", 412.5),
        ("1 234,5", 1234.5),
        ("8 123", 8123.0),
        ("", None),
        (None, None),
    ],
)
def test_tall_fra_snarveier(inn, ut):
    assert tolk_tall(inn) == ut


@pytest.mark.parametrize("inn", [True, "mange", "nan", "inf", [1]])
def test_ugyldige_tall(inn):
    with pytest.raises(ValueError):
        tolk_tall(inn)


# ---------- Mottak ----------


def test_lagrer_helsedata_med_x_api_key(api, nokkel, session):
    svar = api.post("/api/helsedata", json=GYLDIG, headers={"X-API-Key": nokkel})
    assert svar.status_code == 200, svar.text
    assert svar.json() == {"status": "lagret", "dato": "2026-11-02"}
    assert malinger(session) == {
        "skritt": 8123.0,
        "aktiv_energi": 412.5,
        "treningsminutter": 35.0,
        "staatimer": 10.0,
    }
    assert session.exec(select(IngestNokkel)).one().sist_brukt is not None


def test_godtar_ogsa_bearer(api, nokkel):
    svar = api.post("/api/helsedata", json=GYLDIG, headers={"Authorization": f"Bearer {nokkel}"})
    assert svar.status_code == 200


def test_samme_dag_igjen_oppdaterer_og_beholder_manglende_felt(api, nokkel, session):
    api.post("/api/helsedata", json=GYLDIG, headers={"X-API-Key": nokkel})
    api.post(
        "/api/helsedata",
        json={"dato": "2026-11-02", "skritt": 9000, "aktiv_energi": ""},
        headers={"X-API-Key": nokkel},
    )
    lagret = malinger(session)
    assert lagret["skritt"] == 9000.0
    assert lagret["aktiv_energi"] == 412.5  # tomt felt overskriver ikke


@pytest.mark.parametrize(
    "headere",
    [{}, {"X-API-Key": "feil"}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer "}],
)
def test_avviser_uten_gyldig_nokkel(api, nokkel, session, headere):
    svar = api.post("/api/helsedata", json=GYLDIG, headers=headere)
    assert svar.status_code == 401
    assert svar.headers["www-authenticate"] == "Bearer"
    assert malinger(session) == {}


def test_tilbakekalt_nokkel_avvises(api, nokkel, session):
    verktoy.tilbakekall(session, "iPhone")
    assert api.post("/api/helsedata", json=GYLDIG, headers={"X-API-Key": nokkel}).status_code == 401


def test_innloggingscookie_gir_ikke_tilgang_til_api(api, session):
    token = "sesjon-for-nettleser"
    session.add(
        Sesjon(token_hash=hash_token(token), utloper=naa() + SESJON_LEVETID, sist_sett=naa())
    )
    session.flush()
    api.cookies.set("sesjon", token)
    assert api.post("/api/helsedata", json=GYLDIG).status_code == 401


@pytest.mark.parametrize(
    ("data", "melding"),
    [
        ({**GYLDIG, "puls": 60}, "ukjent felt: puls"),
        ({**GYLDIG, "skritt": 250_000}, "skritt"),
        ({**GYLDIG, "skritt": -1}, "skritt"),
        ({**GYLDIG, "skritt": True}, "skritt"),
        ({**GYLDIG, "staatimer": 25}, "staatimer"),
        ({**GYLDIG, "dato": "2.11.2026"}, "dato"),
        ({**GYLDIG, "dato": (naa().date() + timedelta(days=3)).isoformat()}, "fremtiden"),
        ({"skritt": 1}, "dato"),
    ],
)
def test_ugyldige_data_avvises_med_forklaring(api, nokkel, session, data, melding):
    svar = api.post("/api/helsedata", json=data, headers={"X-API-Key": nokkel})
    assert svar.status_code == 400
    assert melding in svar.json()["feil"]
    assert malinger(session) == {}


def test_for_stor_foresporsel_avvises(api, nokkel):
    svar = api.post(
        "/api/helsedata",
        content=b'{"dato": "2026-11-02", "x": "' + b"a" * 20_000 + b'"}',
        headers={"X-API-Key": nokkel, "Content-Type": "application/json"},
    )
    assert svar.status_code == 413


# ---------- Nøkler ----------


def test_nokkelen_lagres_bare_som_hash(session):
    nokkel = verktoy.ny_nokkel(session, "Test")
    rad = session.exec(select(IngestNokkel).where(IngestNokkel.navn == "Test")).one()
    assert nokkel.startswith("dsh_")
    assert len(nokkel) > 40
    assert rad.nokkel_hash == hash_token(nokkel)
    assert nokkel not in rad.nokkel_hash


def test_to_nokler_kan_ikke_ha_samme_navn(session):
    verktoy.ny_nokkel(session, "iPhone")
    with pytest.raises(ValueError, match="finnes allerede"):
        verktoy.ny_nokkel(session, "iPhone")


# ---------- Aktivitetsboksen ----------


def test_aktivitetsboksen_viser_gaarsdagens_tall(session):
    app_ = lag_app(settings_for())
    app_.dependency_overrides[hent_session] = lambda: session
    klient = lag_testklient(app_)
    session.add(Sesjon(token_hash=hash_token("t"), utloper=naa() + SESJON_LEVETID, sist_sett=naa()))
    i_gaar = naa().date() - timedelta(days=1)
    session.add(Dagsmaling(dato=i_gaar, maling="skritt", verdi=12345, kilde="test"))
    session.add(Dagsmaling(dato=naa().date(), maling="skritt", verdi=99, kilde="test"))
    session.flush()
    klient.cookies.set("sesjon", "t")

    svar = klient.get("/boks/aktivitet")
    assert "12 345" in svar.text  # i går, med mellomrom som tusenskille
    assert "99" not in svar.text  # i dag vises ikke
    assert svar.text.count("–") == 3  # de tre som mangler
    assert "av 12" in svar.text  # ståmålet som på klokka


def test_aktivitetsboksen_uten_data(innlogget_klient):
    assert "Ingen aktivitetsdata" in innlogget_klient.get("/boks/aktivitet").text


@pytest.fixture
def innlogget_klient(session: Session):
    app_ = lag_app(settings_for())
    app_.dependency_overrides[hent_session] = lambda: session
    klient = lag_testklient(app_)
    session.add(Sesjon(token_hash=hash_token("t"), utloper=naa() + SESJON_LEVETID, sist_sett=naa()))
    session.flush()
    klient.cookies.set("sesjon", "t")
    return klient


# ---------- Import fra v1 ----------


def test_importerer_helsedata_db_fra_v1(session, tmp_path):
    fil = tmp_path / "helsedata.db"
    with sqlite3.connect(fil) as v1:
        # Samme skjema som v1, inkludert den gamle kolonnen oppreist_timer
        v1.execute(
            "CREATE TABLE dagsaktivitet (dato TEXT PRIMARY KEY, skritt REAL, aktiv_energi REAL,"
            " treningsminutter REAL, oppreist_timer REAL, mottatt TEXT NOT NULL,"
            " oppreist_minutter REAL)"
        )
        v1.execute("INSERT INTO dagsaktivitet VALUES ('2026-10-30', 7000, 300, 20, 12, 'x', NULL)")
        v1.execute("INSERT INTO dagsaktivitet VALUES ('2026-10-31', 9000, 500, 45, NULL, 'x', 700)")
    assert verktoy.importer_helsedata(session, str(fil)) == 2
    rader = {
        (r.dato.isoformat(), r.maling): r.verdi for r in session.exec(select(Dagsmaling)).all()
    }
    assert rader[("2026-10-30", "skritt")] == 7000
    assert ("2026-10-30", "oppreist_minutter") not in rader  # NULL hoppes over
    assert rader[("2026-10-31", "oppreist_minutter")] == 700
    assert {r.kilde for r in session.exec(select(Dagsmaling)).all()} == {"v1-import"}


def test_gamle_oppreist_minutter_godtas_fortsatt(api, nokkel, session):
    """Den gamle snarvei-handlingen og historikken fra v1 sender fortsatt dette feltet."""
    data = {"dato": "2026-11-02", "oppreist_minutter": 720}
    assert api.post("/api/helsedata", json=data, headers={"X-API-Key": nokkel}).status_code == 200
    assert malinger(session) == {"oppreist_minutter": 720.0}


def test_aktivitetsboksen_viser_staatimer(innlogget_klient, session):
    session.add(
        Dagsmaling(dato=naa().date() - timedelta(days=1), maling="staatimer", verdi=9, kilde="t")
    )
    session.flush()
    svar = innlogget_klient.get("/boks/aktivitet").text
    assert "Ståtimer" in svar
    assert "9<small> av 12" in svar
    assert "Oppreist" not in svar


@pytest.mark.parametrize(
    "per_time",
    [
        "0\n3\n0\n1,5\n12",  # slik Snarveier setter en liste inn i et tekstfelt
        [0, 3, 0, 1.5, 12],  # som JSON-liste
        "0;3;0;1,5;12",
    ],
)
def test_staatimer_telles_fra_staatid_per_time(api, nokkel, session, per_time):
    data = {"dato": "2026-11-02", "staatid_per_time": per_time}
    svar = api.post("/api/helsedata", json=data, headers={"X-API-Key": nokkel})
    assert svar.status_code == 200, svar.text
    assert malinger(session) == {"staatimer": 3.0}  # tre timer med mer enn 0 minutter


@pytest.mark.parametrize("per_time", ["5\n61", "-1", [1] * 26, "mye", {"a": 1}])
def test_ugyldig_staatid_per_time_avvises(api, nokkel, session, per_time):
    data = {"dato": "2026-11-02", "staatid_per_time": per_time}
    svar = api.post("/api/helsedata", json=data, headers={"X-API-Key": nokkel})
    assert svar.status_code == 400
    assert "staatid_per_time" in svar.json()["feil"]
    assert malinger(session) == {}
