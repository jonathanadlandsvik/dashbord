"""Vær, bysykkel og kalender. Ingen ekte nettverkskall: respx svarer i stedet."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlmodel import Session

from app.auth import SESJON_LEVETID, hash_token, naa
from app.db import hent_session
from app.main import lag_app
from app.models import ApiCache, Sesjon
from app.services import bysykkel, kalender, yr
from app.tid import OSLO
from tests.conftest import lag_testklient, settings_for

NAA = datetime(2026, 11, 3, 15, 20, tzinfo=OSLO)  # 14:20 UTC


# ---------- Testdata i samme format som tjenestene ----------


def yr_data(start: datetime = datetime(2026, 11, 3, 13, 0, tzinfo=UTC)) -> dict:
    serie = []
    for i in range(16):
        tid = start + timedelta(hours=i)
        punkt = {
            "time": tid.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": {
                "instant": {"details": {"air_temperature": 4.0 + i, "wind_speed": 3.2}},
                "next_1_hours": {
                    "summary": {"symbol_code": "lightrain" if i % 2 else "cloudy"},
                    "details": {"precipitation_amount": 0.5 if i % 2 else 0.0},
                },
            },
        }
        serie.append(punkt)
    serie.append(  # lenger frem: bare 6-timers intervaller
        {
            "time": (start + timedelta(hours=18)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": {
                "instant": {"details": {"air_temperature": 1.0}},
                "next_6_hours": {"summary": {"symbol_code": "snow"}, "details": {}},
            },
        }
    )
    return {"type": "Feature", "properties": {"timeseries": serie}}


GBFS_STATUS = {
    "data": {
        "stations": [
            {"station_id": "1", "num_bikes_available": 9, "num_docks_available": 1},
            {
                "station_id": "293",
                "is_renting": True,
                "num_bikes_available": 5,
                "num_docks_available": 12,
                "last_reported": 1793714400,
                "vehicle_types_available": [
                    {"vehicle_type_id": "bike", "count": 3},
                    {"vehicle_type_id": "ebike", "count": 2},
                ],
            },
        ]
    }
}
GBFS_INFO = {"data": {"stations": [{"station_id": "293", "name": "S. P. Andersens vei"}]}}


def google_settings(**ekstra):
    return settings_for(
        google_client_id="klient",
        google_client_secret="hemmelig",
        google_refresh_token="refresh",
        **ekstra,
    )


@pytest.fixture(autouse=True)
def tom_tokencache():
    kalender._token.clear()
    yield
    kalender._token.clear()


# ---------- Yr ----------


@pytest.mark.parametrize(
    ("kode", "tekst"),
    [
        ("clearsky_day", "Klarvær"),
        ("partlycloudy_night", "Delvis skyet"),
        ("lightrain", "Lett regn"),
        ("heavysnowshowersandthunder_polartwilight", "Kraftige snøbyger og torden"),
        ("noeheltnytt", "Ukjent vær"),
    ],
)
def test_symbolkoder_blir_norsk_tekst(kode, tekst):
    assert yr.beskriv(kode) == tekst


def test_yr_tolkes_fra_denne_timen():
    vaer = yr.tolk(yr_data(), NAA)
    assert vaer.temperatur == 5.0  # 14:00 UTC, timen før er hoppet over
    assert vaer.beskrivelse == "Lett regn"
    assert vaer.timer[0].klokke == "15"  # norsk tid
    assert len(vaer.timer) == 12
    assert vaer.nedbor_6t == 1.5  # tre av de seks første timene har 0,5 mm


def test_yr_stopper_der_timeintervallene_slutter():
    data = yr_data()
    data["properties"]["timeseries"] = data["properties"]["timeseries"][-3:]
    vaer = yr.tolk(data, NAA)
    assert len(vaer.timer) == 2


@respx.mock
def test_yr_caches_og_respekterer_expires(session: Session):
    utloper = "Tue, 03 Nov 2026 15:00:00 GMT"
    rute = respx.get(yr.URL).mock(
        return_value=httpx.Response(
            200,
            json=yr_data(),
            headers={"Expires": utloper, "Last-Modified": "Tue, 03 Nov 2026 14:00:00 GMT"},
        )
    )
    settings = settings_for(vaer_lat=63.430512, vaer_lon=10.395134)
    klient = httpx.Client()

    yr.hent_vaer(session, settings, NAA, klient)
    yr.hent_vaer(session, settings, NAA + timedelta(minutes=10), klient)
    assert rute.call_count == 1  # andre gang fra cachen

    forespørsel = rute.calls[0].request
    assert forespørsel.url.params["lat"] == "63.4305"  # maks 4 desimaler
    assert "github.com/jonathanadlandsvik" in forespørsel.headers["User-Agent"]

    cache = session.get(ApiCache, "yr:63.4305,10.3951")
    assert cache.utloper == datetime(2026, 11, 3, 15, 0, tzinfo=UTC)


@respx.mock
def test_yr_sender_if_modified_since_og_godtar_304(session: Session):
    settings = settings_for()
    session.add(
        ApiCache(
            nokkel="yr:63.4305,10.3951",
            innhold=yr_data(),
            utloper=NAA - timedelta(minutes=1),
            sist_endret="Tue, 03 Nov 2026 13:00:00 GMT",
        )
    )
    session.flush()
    rute = respx.get(yr.URL).mock(return_value=httpx.Response(304))

    vaer = yr.hent_vaer(session, settings, NAA, httpx.Client())
    assert rute.calls[0].request.headers["If-Modified-Since"] == "Tue, 03 Nov 2026 13:00:00 GMT"
    assert vaer.temperatur == 5.0
    assert not vaer.utdatert


@respx.mock
def test_yr_viser_forrige_melding_hvis_tjenesten_er_nede(session: Session):
    session.add(
        ApiCache(nokkel="yr:63.4305,10.3951", innhold=yr_data(), utloper=NAA - timedelta(hours=1))
    )
    session.flush()
    respx.get(yr.URL).mock(side_effect=httpx.ConnectTimeout("treg"))
    assert yr.hent_vaer(session, settings_for(), NAA, httpx.Client()).utdatert


@respx.mock
def test_yr_uten_cache_og_uten_svar_gir_feil(session: Session):
    respx.get(yr.URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        yr.hent_vaer(session, settings_for(), NAA, httpx.Client())


# ---------- Bysykkel ----------


def test_bysykkel_tolkes():
    stasjon = bysykkel.tolk(GBFS_STATUS, GBFS_INFO, "293")
    assert (stasjon.navn, stasjon.sykler, stasjon.elsykler, stasjon.ledige_plasser) == (
        "S. P. Andersens vei",
        3,
        2,
        12,
    )
    assert stasjon.i_drift


def test_bysykkel_uten_kjoretoytyper_bruker_totalen():
    stasjon = bysykkel.tolk(GBFS_STATUS, {"data": {"stations": []}}, "1")
    assert (stasjon.navn, stasjon.sykler, stasjon.elsykler) == ("Stasjon 1", 9, 0)


def test_ukjent_stasjon_gir_feil():
    with pytest.raises(LookupError):
        bysykkel.tolk(GBFS_STATUS, GBFS_INFO, "999")


@respx.mock
def test_bysykkel_hentes():
    respx.get(f"{bysykkel.BASE}/station_status.json").respond(json=GBFS_STATUS)
    respx.get(f"{bysykkel.BASE}/station_information.json").respond(json=GBFS_INFO)
    stasjon = asyncio.run(bysykkel.hent_stasjon(settings_for()))
    assert stasjon.sykler == 3


# ---------- Kalender ----------


def test_kalender_sorterer_og_filtrerer():
    svar = [
        {
            "items": [
                {"summary": "Forelesning", "start": {"dateTime": "2026-11-03T10:15:00+01:00"}},
                {
                    "summary": "Avlyst",
                    "status": "cancelled",
                    "start": {"dateTime": "2026-11-03T08:00:00+01:00"},
                },
            ]
        },
        {
            "items": [
                {"summary": "Bursdag", "start": {"date": "2026-11-03"}},
                {"summary": "Nattskift", "start": {"dateTime": "2026-11-02T22:00:00+01:00"}},
                {"start": {"dateTime": "2026-11-03T09:00:00Z"}},
            ]
        },
    ]
    hendelser = kalender.tolk(svar, NAA.date())
    assert [(h.tid, h.tittel) for h in hendelser] == [
        ("Hele dagen", "Bursdag"),
        ("Pågår", "Nattskift"),
        ("10:00", "(uten tittel)"),  # 09:00 UTC er 10:00 norsk tid
        ("10:15", "Forelesning"),
    ]


@respx.mock
def test_kalender_henter_fra_alle_kalendere_utenom_ukenumre():
    token = respx.post(kalender.TOKEN_URL).respond(
        json={"access_token": "tilgang", "expires_in": 3600}
    )
    respx.get(f"{kalender.API}/users/me/calendarList").respond(
        json={
            "items": [
                {"id": "jonathan@example.com", "summary": "Jonathan"},
                {"id": "uke#nr@group.v.calendar.google.com", "summary": "Ukenumre"},
                {"id": "skjult@example.com", "summary": "Skjult", "hidden": True},
                {"id": "ntnu@example.com", "summary": "NTNU"},
            ]
        }
    )
    hendelser_rute = respx.get(url__regex=rf"{kalender.API}/calendars/.+/events").respond(
        json={"items": [{"summary": "Møte", "start": {"dateTime": "2026-11-03T12:00:00+01:00"}}]}
    )

    settings = google_settings()
    hendelser = asyncio.run(kalender.hent_dagens(settings, NAA))
    assert len(hendelser) == 2
    assert hendelser_rute.call_count == 2
    sendt = token.calls[0].request
    assert b"grant_type=refresh_token" in sendt.content
    assert hendelser_rute.calls[0].request.headers["Authorization"] == "Bearer tilgang"
    assert hendelser_rute.calls[0].request.url.params["timeMin"] == "2026-11-03T00:00:00+01:00"

    asyncio.run(kalender.hent_dagens(settings, NAA))
    assert token.call_count == 1  # access tokenet gjenbrukes


@respx.mock
def test_utlopt_refresh_token_gir_egen_feil():
    respx.post(kalender.TOKEN_URL).respond(400, json={"error": "invalid_grant"})
    with pytest.raises(kalender.KalenderTilgangFeil):
        asyncio.run(kalender.hent_dagens(google_settings(), NAA))


def test_manglende_google_nokler_gir_egen_feil():
    with pytest.raises(kalender.KalenderTilgangFeil):
        asyncio.run(kalender.hent_dagens(settings_for(), NAA))


# ---------- Rutene ----------


@pytest.fixture
def innlogget(session: Session):
    app_ = lag_app(settings_for())
    app_.dependency_overrides[hent_session] = lambda: session
    klient = lag_testklient(app_)
    token = "test-sesjon"
    session.add(
        Sesjon(token_hash=hash_token(token), utloper=naa() + SESJON_LEVETID, sist_sett=naa())
    )
    session.flush()
    klient.cookies.set("sesjon", token)
    return klient


@pytest.fixture
def uinnlogget(session: Session):
    app_ = lag_app(settings_for())
    app_.dependency_overrides[hent_session] = lambda: session
    return lag_testklient(app_)


@pytest.mark.parametrize("boks", ["vaer", "bysykkel", "kalender"])
def test_boksene_krever_innlogging(uinnlogget, boks):
    svar = uinnlogget.get(f"/boks/{boks}", headers={"HX-Request": "true"})
    assert svar.status_code == 401


def test_appen_bruker_aldri_databasen_fra_env(klient):
    """Uten DATABASE_URL i appens egne innstillinger skal den ikke finne en annen."""
    from app.db import hent_engine

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        hent_engine(klient.app)


def test_forsiden_laster_boksene_med_htmx(innlogget):
    side = innlogget.get("/").text
    for boks in ("vaer", "bysykkel", "kalender"):
        assert f'hx-get="/boks/{boks}"' in side


def test_kalenderboksen_escaper_titler(innlogget, monkeypatch):
    async def falsk(*_):
        return [kalender.Hendelse(tid="12:00", tittel="<script>alert(1)</script>", sortering=NAA)]

    monkeypatch.setattr(kalender, "hent_dagens", falsk)
    svar = innlogget.get("/boks/kalender")
    assert "<script>alert" not in svar.text
    assert "&lt;script&gt;" in svar.text


def test_feil_i_en_tjeneste_gir_vennlig_melding(innlogget, monkeypatch):
    async def feiler(*_):
        raise httpx.ConnectError("intern detalj som ikke skal vises")

    monkeypatch.setattr(bysykkel, "hent_stasjon", feiler)
    svar = innlogget.get("/boks/bysykkel")
    assert svar.status_code == 200
    assert "Fikk ikke hentet bysykler" in svar.text
    assert "intern detalj" not in svar.text


def test_utlopt_google_tilgang_forklares(innlogget, monkeypatch):
    async def utlopt(*_):
        raise kalender.KalenderTilgangFeil("x")

    monkeypatch.setattr(kalender, "hent_dagens", utlopt)
    assert "GOOGLE_REFRESH_TOKEN" in innlogget.get("/boks/kalender").text


@respx.mock
def test_vaerboksen_viser_temperatur(innlogget, monkeypatch):
    monkeypatch.setattr("app.routers.bokser.naa", lambda: NAA)
    respx.get(yr.URL).respond(json=yr_data(), headers={"Expires": "Tue, 03 Nov 2026 15:00:00 GMT"})
    svar = innlogget.get("/boks/vaer")
    assert "5°" in svar.text
    assert "Lett regn" in svar.text
    assert "Yr / MET Norway" in svar.text
