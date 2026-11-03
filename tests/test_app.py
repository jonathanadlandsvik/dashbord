def test_healthz(klient):
    svar = klient.get("/healthz")
    assert svar.status_code == 200
    assert svar.json() == {"status": "ok"}


def test_forside_viser_dato_og_bokser(klient):
    svar = klient.get("/")
    assert svar.status_code == 200
    assert "text/html" in svar.headers["content-type"]
    for tekst in ("uke", "Vær", "Bysykkel", "Kalender", "Kveldens vaner"):
        assert tekst in svar.text


def test_statiske_filer_serveres(klient):
    assert klient.get("/static/css/app.css").status_code == 200
    assert klient.get("/static/js/htmx-2.0.4.min.js").status_code == 200


def test_api_dokumentasjon_finnes_lokalt(klient):
    assert klient.get("/docs").status_code == 200


def test_api_dokumentasjon_er_skjult_i_produksjon(prod_klient):
    assert prod_klient.get("/docs").status_code == 404
    assert prod_klient.get("/openapi.json").status_code == 404
