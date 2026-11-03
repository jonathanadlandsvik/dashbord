"""Sikkerhet som ikke trenger database: headere, Origin-sjekk og konfigurasjon."""

import pytest
from pydantic import ValidationError

from tests.conftest import HEMMELIG, settings_for


def test_sikkerhetsheadere_settes(klient):
    svar = klient.get("/healthz")
    csp = svar.headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp
    assert svar.headers["x-content-type-options"] == "nosniff"
    assert svar.headers["referrer-policy"] == "same-origin"
    assert "strict-transport-security" not in svar.headers  # bare i produksjon


def test_hsts_i_produksjon(prod_klient):
    assert "max-age=" in prod_klient.get("/healthz").headers["strict-transport-security"]


@pytest.mark.parametrize(
    "headere",
    [
        {"Origin": "https://ondsinnet.example"},
        {"Origin": ""},
        {"Origin": "", "Referer": "https://ondsinnet.example/side"},
    ],
)
def test_post_fra_annet_nettsted_avvises(klient, headere):
    svar = klient.post("/logg-ut", headers=headere)
    assert svar.status_code == 403
    assert "annet nettsted" in svar.text


def test_api_ruter_er_unntatt_origin_sjekken(klient):
    # /api/ er for iPhone-snarveien, som ikke er en nettleser. Den bruker nøkkel (fase 5).
    svar = klient.post("/api/finnes-ikke", headers={"Origin": ""})
    assert svar.status_code == 404


def test_produksjon_krever_https():
    with pytest.raises(ValidationError, match="https"):
        settings_for(app_env="production", app_base_url="http://dashbord.vercel.app")


def test_produksjon_krever_langt_session_secret():
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        settings_for(app_env="production", session_secret="for-kort")
    settings_for(app_env="production", session_secret=HEMMELIG)  # ok


def test_passkey_domenet_utledes_fra_adressen():
    settings = settings_for(app_base_url="https://dashbord-abc.vercel.app/")
    assert settings.origin == "https://dashbord-abc.vercel.app"
    assert settings.rp_id == "dashbord-abc.vercel.app"
