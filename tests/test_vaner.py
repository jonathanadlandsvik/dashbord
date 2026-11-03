"""Vanene: reglene for ukestatus, avkrysning, ukeoppsummering og historikk."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from app import vaner
from app.auth import SESJON_LEVETID, hash_token, naa
from app.db import hent_session
from app.main import lag_app
from app.models import ALLE_DAGER, HVERDAGER, Avkrysning, Sesjon, Ukeoppsummering, Vane
from app.tid import OSLO
from tests.conftest import lag_testklient, settings_for

MAN = date(2026, 11, 2)  # uke 45, samme mandag som vanene startet
ONS = MAN + timedelta(days=2)
LOR = MAN + timedelta(days=5)
SON = MAN + timedelta(days=6)


def vane(id_: int, ukemal: int, dager=ALLE_DAGER, fra=MAN, til=None) -> Vane:
    return Vane(
        id=id_, nokkel=f"v{id_}", navn=f"Vane {id_}", formulering="", ukemal=ukemal,
        ukedager=dager, aktiv_fra=fra, aktiv_til=til,
    )  # fmt: skip


def gjort(v: Vane, *dager: date) -> set:
    return {(v.id, d) for d in dager}


# ---------- Reglene, uten database ----------


def test_trening_to_ganger_er_mulig_midt_i_uka():
    trening = vane(1, 2)
    status = vaner.ukestatus(trening, MAN, set(), i_dag=ONS)
    assert (status.antall, status.mal, status.tilstand) == (0, 2, vaner.Tilstand.MULIG)


def test_trening_ikke_nadd_nar_det_er_for_sent():
    trening = vane(1, 2)
    status = vaner.ukestatus(trening, MAN, gjort(trening, ONS), i_dag=SON)
    assert status.tilstand == vaner.Tilstand.MULIG  # søndag kan fortsatt krysses av
    status = vaner.ukestatus(trening, MAN, set(), i_dag=SON)
    assert status.tilstand == vaner.Tilstand.IKKE_NADD


def test_nadd_nar_malet_er_oppfylt():
    trening = vane(1, 2)
    status = vaner.ukestatus(trening, MAN, gjort(trening, MAN, ONS), i_dag=ONS)
    assert status.tilstand == vaner.Tilstand.NADD


def test_hverdagsvane_gjelder_ikke_i_helgen():
    opp = vane(2, 5, dager=HVERDAGER)
    status = vaner.ukestatus(opp, MAN, gjort(opp, MAN, ONS), i_dag=LOR)
    assert [g for _, g in status.dager][5:] == [None, None]  # lørdag og søndag
    assert status.mal == 5
    assert status.tilstand == vaner.Tilstand.IKKE_NADD  # ingen hverdager igjen
    assert not vaner.gjelder(opp, LOR)


def test_vane_som_starter_midt_i_uka_far_lavere_mal_den_uka():
    ny = vane(3, 7, fra=date(2026, 11, 5))  # torsdag
    status = vaner.ukestatus(ny, MAN, set(), i_dag=ONS)
    assert status.mal == 4  # torsdag til søndag


def test_avsluttet_vane_gjelder_ikke_lenger():
    gammel = vane(4, 7, til=ONS)
    assert vaner.gjelder(gammel, MAN)
    assert not vaner.gjelder(gammel, ONS)


def test_andel_nadd_teller_ikke_mer_enn_malet():
    trening = vane(1, 2)
    kreatin = vane(5, 7)
    statuser = [
        vaner.ukestatus(trening, MAN, gjort(trening, MAN, ONS, LOR), i_dag=SON),  # 3 av 2
        vaner.ukestatus(kreatin, MAN, gjort(kreatin, MAN), i_dag=SON),  # 1 av 7
    ]
    assert vaner.andel_nadd(statuser) == round(100 * 3 / 9)
    assert vaner.andel_nadd([]) is None


# ---------- Med database ----------


FAST_NAA = datetime(2026, 11, 4, 21, 0, tzinfo=OSLO)  # onsdag kveld


@pytest.fixture
def klient(session: Session, monkeypatch):
    monkeypatch.setattr("app.routers.vaner.naa", lambda: FAST_NAA)
    monkeypatch.setattr("app.routers.bokser.naa", lambda: FAST_NAA)
    app_ = lag_app(settings_for())
    app_.dependency_overrides[hent_session] = lambda: session
    k = lag_testklient(app_)
    session.add(Sesjon(token_hash=hash_token("t"), utloper=naa() + SESJON_LEVETID, sist_sett=naa()))
    session.flush()
    k.cookies.set("sesjon", "t")
    return k


def csrf(klient) -> dict:
    side = klient.get("/vaner").text
    return {"X-CSRF-Token": side.split('name="csrf-token" content="')[1].split('"')[0]}


def vane_id(session: Session, nokkel: str) -> int:
    return session.exec(select(Vane.id).where(Vane.nokkel == nokkel)).one()


def test_vanesiden_krever_innlogging(session):
    app_ = lag_app(settings_for())
    app_.dependency_overrides[hent_session] = lambda: session
    svar = lag_testklient(app_).get("/vaner", follow_redirects=False)
    assert svar.headers["location"] == "/logg-inn"


def test_vanesiden_viser_dagens_vaner(klient):
    side = klient.get("/vaner").text
    for navn in ("Instagram", "Opp med en gang", "Mobilfri morgen", "Kreatin", "Trening"):
        assert navn in side
    assert "0 av 6 gjort" in side


def test_hverdagsvanen_vises_ikke_pa_lordag(klient, monkeypatch):
    monkeypatch.setattr("app.routers.vaner.naa", lambda: datetime(2026, 11, 7, 21, tzinfo=OSLO))
    side = klient.get("/vaner").text
    assert "Opp med en gang</span>" not in side
    assert "0 av 5 gjort" in side


def test_kryss_av_og_fjern_igjen(klient, session):
    trening = vane_id(session, "trening")
    data = {"vane_id": trening, "dato": "2026-11-04"}

    svar = klient.post("/vaner/kryss", data=data, headers=csrf(klient))
    assert svar.status_code == 200
    assert 'aria-pressed="true"' in svar.text
    assert 'id="uka" hx-swap-oob="innerHTML"' in svar.text  # uka oppdateres samtidig
    assert "1 av 6 gjort" in svar.text
    assert session.get(Avkrysning, (trening, date(2026, 11, 4))) is not None

    svar = klient.post("/vaner/kryss", data=data, headers=csrf(klient))
    assert 'aria-pressed="false"' in svar.text
    assert session.get(Avkrysning, (trening, date(2026, 11, 4))) is None


def test_avkrysning_krever_csrf(klient, session):
    data = {"vane_id": vane_id(session, "trening"), "dato": "2026-11-04"}
    assert klient.post("/vaner/kryss", data=data).status_code == 403


@pytest.mark.parametrize(
    ("nokkel", "dato"),
    [
        ("trening", "2026-11-05"),  # i morgen
        ("trening", "2026-10-27"),  # mer enn en uke siden
        ("trening", "2026-11-01"),  # før vanen startet
    ],
)
def test_ugyldige_avkrysninger_avvises(klient, session, nokkel, dato):
    data = {"vane_id": vane_id(session, nokkel), "dato": dato}
    assert klient.post("/vaner/kryss", data=data, headers=csrf(klient)).status_code == 400


def test_hverdagsvane_kan_ikke_krysses_av_i_helgen(klient, session, monkeypatch):
    monkeypatch.setattr("app.routers.vaner.naa", lambda: datetime(2026, 11, 8, 21, tzinfo=OSLO))
    data = {"vane_id": vane_id(session, "opp"), "dato": "2026-11-07"}
    assert klient.post("/vaner/kryss", data=data, headers=csrf(klient)).status_code == 400


def test_kan_rette_gaarsdagen(klient, session):
    side = klient.get("/vaner?dato=2026-11-03").text
    assert "tirsdag 3. nov." in side
    data = {"vane_id": vane_id(session, "kreatin"), "dato": "2026-11-03"}
    assert klient.post("/vaner/kryss", data=data, headers=csrf(klient)).status_code == 200


def test_fremtidig_dag_sender_tilbake_til_i_dag(klient):
    svar = klient.get("/vaner?dato=2026-11-05", follow_redirects=False)
    assert svar.status_code == 303


def test_ukeoppsummering_lagres_med_norsk_komma(klient, session):
    svar = klient.post(
        "/vaner/uke/2026-11-02",
        data={"skjermtid": "3,45", "refleksjon": "  Mobilen i gangen  "},
        headers=csrf(klient),
    )
    assert "Lagret." in svar.text
    lagret = session.get(Ukeoppsummering, MAN)
    assert lagret.skjermtid_timer == Decimal("3.5")  # rundet til én desimal
    assert lagret.refleksjon == "Mobilen i gangen"


@pytest.mark.parametrize("verdi", ["25", "-1", "mye"])
def test_ugyldig_skjermtid_gir_melding(klient, session, verdi):
    svar = klient.post("/vaner/uke/2026-11-02", data={"skjermtid": verdi}, headers=csrf(klient))
    assert "mellom 0 og 24" in svar.text
    assert session.get(Ukeoppsummering, MAN) is None


@pytest.mark.parametrize("start", ["2026-11-03", "2026-11-09"])  # ikke mandag / fremtidig uke
def test_ugyldig_uke_avvises(klient, start):
    svar = klient.post(f"/vaner/uke/{start}", data={"skjermtid": "2"}, headers=csrf(klient))
    assert svar.status_code == 400


def test_historikk_viser_atte_uker_med_prosent_og_skjermtid(klient, session):
    session.add(Ukeoppsummering(uke_start=MAN, skjermtid_timer=Decimal("3.1")))
    for nokkel in ("instagram", "kreatin"):
        session.add(Avkrysning(vane_id=vane_id(session, nokkel), dato=MAN))
    session.flush()
    historikk = vaner.historikk(session, ONS)
    assert len(historikk) == 1  # uker fra før vanene startet vises ikke
    assert historikk[-1].start == MAN
    assert historikk[-1].skjermtid == Decimal("3.1")
    assert historikk[-1].prosent == round(100 * 2 / (7 + 5 + 7 + 7 + 2 + 5))

    senere = vaner.historikk(session, MAN + timedelta(weeks=10))
    assert len(senere) == vaner.ANTALL_UKER_HISTORIKK  # aldri mer enn åtte uker

    side = klient.get("/vaner").text
    assert "3,1 t" in side
    assert 'class="over"' in side  # over målet på 2,5


def test_forsideboksen_teller_dagens_vaner(klient, session):
    session.add(Avkrysning(vane_id=vane_id(session, "kreatin"), dato=ONS))
    session.flush()
    svar = klient.get("/boks/vaner").text
    assert '<span class="stor">1</span>' in svar
    assert "av 6 i dag" in svar


def test_endret_mal_gjelder_bare_fremover(session):
    """Ny versjon av en vane: gamle uker vurderes mot det gamle målet."""
    gammel = session.exec(select(Vane).where(Vane.nokkel == "trening")).one()
    gammel.aktiv_til = date(2026, 11, 9)
    session.add(gammel)
    session.add(
        Vane(nokkel="trening", navn="Trening", formulering="Trente", ukemal=3,
             ukedager=ALLE_DAGER, sortering=gammel.sortering, aktiv_fra=date(2026, 11, 9))
    )  # fmt: skip
    session.flush()
    uke45 = {s.vane.nokkel: s.mal for s in vaner.uke(session, MAN, ONS)}
    uke46 = {s.vane.nokkel: s.mal for s in vaner.uke(session, date(2026, 11, 9), date(2026, 11, 9))}
    assert uke45["trening"] == 2
    assert uke46["trening"] == 3
