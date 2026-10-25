import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

API_URL = "https://jonathwa.pythonanywhere.com/helsedata"


@st.cache_data(ttl=600)
def hent_treningsdata(dato):
    """Henter tallene for én dag. Returnerer (data, feilmelding)."""
    try:
        lese_nokkel = st.secrets["helse"]["lese_nokkel"]
    except KeyError:
        return None, "Mangler `lese_nokkel` under `[helse]` i secrets."

    try:
        response = requests.get(
            f"{API_URL}/{dato}",
            headers={"Authorization": f"Bearer {lese_nokkel}"},
            timeout=10,
        )
    except requests.exceptions.RequestException:
        return None, "Får ikke kontakt med helse-API-et."

    if response.status_code == 200:
        return response.json(), None
    if response.status_code == 404:
        return None, "Ingen aktivitetsdata for i går ennå."
    if response.status_code == 401:
        return None, "Lesenøkkelen ble avvist – sjekk `[helse]` i secrets."
    return None, f"Helse-API-et svarte med feil (HTTP {response.status_code})."


def vis_tall(verdi, format_):
    return "–" if verdi is None else format_(verdi)


def vis_trening():
    st.header("⌚ Aktivitet i går")

    i_gaar = (datetime.now(ZoneInfo("Europe/Oslo")) - timedelta(days=1)).date()
    data, feil = hent_treningsdata(i_gaar.isoformat())

    if feil:
        st.info(feil)
        return

    col1, col2 = st.columns(2)
    col1.metric("👟 Skritt", vis_tall(data["skritt"], lambda v: f"{v:,.0f}".replace(",", " ")))
    col2.metric("🔴 Bevegelse", vis_tall(data["aktiv_energi"], lambda v: f"{v:.0f} kcal"))

    col3, col4 = st.columns(2)
    col3.metric("🟢 Trening", vis_tall(data["treningsminutter"], lambda v: f"{v:.0f} min"))
    col4.metric("🔵 Oppreist", vis_tall(data.get("oppreist_minutter"), lambda v: f"{v:.0f} min"))
