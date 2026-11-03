from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app.db import hent_session, til_sqlalchemy_url
from app.main import lag_app
from app.models import ALLE_DAGER, Avkrysning, Ukeoppsummering, Vane
from tests.conftest import alembic_config, settings_for

# ---------- Uten database ----------


def test_neon_adresse_far_psycopg_driver():
    neon = "postgresql://bruker:hemmelig@ep-x-pooler.eu-central-1.aws.neon.tech/neondb"
    assert til_sqlalchemy_url(neon).startswith("postgresql+psycopg://bruker:hemmelig@")
    assert til_sqlalchemy_url("postgres://a@b/c") == "postgresql+psycopg://a@b/c"


def test_healthz_db_svarer_503_uten_detaljer_nar_databasen_feiler():
    class OdelagtSession:
        def exec(self, *_):
            raise ConnectionError("passord=hemmelig host=ep-x.neon.tech")

    app = lag_app(settings_for())
    app.dependency_overrides[hent_session] = lambda: OdelagtSession()
    svar = TestClient(app).get("/healthz/db")
    assert svar.status_code == 503
    assert svar.json() == {"database": "utilgjengelig"}
    assert "hemmelig" not in svar.text


# ---------- Med database ----------


def test_migrasjonene_matcher_modellene(migrert_engine):
    """Fanger en modell som er endret uten at det er laget en migrasjon."""
    with migrert_engine.connect() as tilkobling:
        forskjeller = compare_metadata(MigrationContext.configure(tilkobling), SQLModel.metadata)
    assert forskjeller == []


def test_migrasjonene_kan_rulles_tilbake_og_kjores_igjen(test_db_url, migrert_engine):
    config = alembic_config(test_db_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_de_seks_vanene_er_lagt_inn(session: Session):
    vaner = session.exec(select(Vane).order_by(Vane.sortering)).all()
    assert [v.nokkel for v in vaner] == [
        "instagram",
        "opp",
        "mobilfri-morgen",
        "kreatin",
        "trening",
        "lese-gitar",
    ]
    opp = vaner[1]
    assert opp.ukedager == [0, 1, 2, 3, 4]
    assert opp.ukemal == 5
    assert all(v.aktiv_fra == date(2026, 11, 2) and v.aktiv_til is None for v in vaner)


def _vane(session: Session, nokkel: str) -> Vane:
    return session.exec(select(Vane).where(Vane.nokkel == nokkel)).one()


def test_samme_vane_kan_bare_krysses_av_en_gang_per_dag(session: Session):
    kreatin = _vane(session, "kreatin")
    session.add(Avkrysning(vane_id=kreatin.id, dato=date(2026, 11, 3)))
    session.flush()
    session.add(Avkrysning(vane_id=kreatin.id, dato=date(2026, 11, 3)))
    with pytest.raises(IntegrityError):
        session.flush()


def test_avkrysning_far_tidsstempel_fra_databasen(session: Session):
    kreatin = _vane(session, "kreatin")
    avkrysning = Avkrysning(vane_id=kreatin.id, dato=date(2026, 11, 3))
    session.add(avkrysning)
    session.flush()
    session.refresh(avkrysning)
    assert avkrysning.registrert is not None


@pytest.mark.parametrize(
    ("ukemal", "ukedager"),
    [
        (6, [0, 1, 2, 3, 4]),  # målet er høyere enn antall dager vanen gjelder
        (0, ALLE_DAGER),  # mål på null
        (1, []),  # ingen dager
        (1, [7]),  # ugyldig ukedag
    ],
)
def test_ugyldige_vaner_avvises_av_databasen(session: Session, ukemal, ukedager):
    session.add(
        Vane(
            nokkel="test",
            navn="Test",
            formulering="Test",
            ukemal=ukemal,
            ukedager=ukedager,
            aktiv_fra=date(2026, 11, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    ("uke_start", "skjermtid"),
    [
        (date(2026, 11, 3), Decimal("2.5")),  # tirsdag, ikke mandag
        (date(2026, 11, 2), Decimal("25.0")),  # mer enn et døgn
    ],
)
def test_ugyldige_ukeoppsummeringer_avvises(session: Session, uke_start, skjermtid):
    session.add(Ukeoppsummering(uke_start=uke_start, skjermtid_timer=skjermtid))
    with pytest.raises(IntegrityError):
        session.flush()


def test_gyldig_ukeoppsummering_lagres(session: Session):
    session.add(Ukeoppsummering(uke_start=date(2026, 11, 2), skjermtid_timer=Decimal("3.4")))
    session.flush()
    lagret = session.get(Ukeoppsummering, date(2026, 11, 2))
    assert lagret.skjermtid_timer == Decimal("3.4")
