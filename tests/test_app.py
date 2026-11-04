def test_healthz(klient):
    svar = klient.get("/healthz")
    assert svar.status_code == 200
    assert svar.json() == {"status": "ok"}


def test_statiske_filer_serveres(klient):
    assert klient.get("/static/css/app.css").status_code == 200
    assert klient.get("/static/js/htmx-2.0.4.min.js").status_code == 200


def test_api_dokumentasjon_finnes_lokalt(klient):
    assert klient.get("/docs").status_code == 200


def test_api_dokumentasjon_er_skjult_i_produksjon(prod_klient):
    assert prod_klient.get("/docs").status_code == 404
    assert prod_klient.get("/openapi.json").status_code == 404


def test_appen_starter_uten_public_mappe(monkeypatch, tmp_path):
    # Slik er det på Vercel: public/ ligger på CDN-et, ikke i funksjonen.
    from fastapi.testclient import TestClient

    import app.main
    from tests.conftest import settings_for

    monkeypatch.setattr(app.main, "PUBLIC", tmp_path / "finnes-ikke")
    klient = TestClient(app.main.lag_app(settings_for(app_env="production")))
    assert klient.get("/healthz").status_code == 200


def test_appen_kan_installeres_pa_hjemskjermen(klient):
    import json
    import struct
    from pathlib import Path

    from app.templating import templates

    hode = templates.get_template("base.html").render(csrf="")
    for tag in ('rel="manifest"', 'rel="apple-touch-icon"', 'name="theme-color"'):
        assert tag in hode

    svar = klient.get("/static/manifest.webmanifest")
    assert svar.status_code == 200
    assert svar.headers["content-type"].startswith("application/manifest+json")
    manifest = json.loads(svar.text)
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert {i["purpose"] for i in manifest["icons"]} == {"any", "maskable"}

    rot = Path(__file__).resolve().parent.parent / "public"
    for ikon in manifest["icons"]:
        fil = rot / ikon["src"].lstrip("/")
        bredde, hoyde = struct.unpack(">II", fil.read_bytes()[16:24])  # PNG-headeren
        assert f"{bredde}x{hoyde}" == ikon["sizes"]

    apple = rot / "static/ikoner/apple-touch-icon.png"
    assert struct.unpack(">II", apple.read_bytes()[16:24]) == (180, 180)
