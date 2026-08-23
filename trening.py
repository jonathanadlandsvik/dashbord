import streamlit as st
import requests
from datetime import datetime, date, timedelta


def hent_siste_treningsdata():
    try:
        response = requests.get("https://jonathwa.pythonanywhere.com/siste")
        if response.status_code == 200:
            return response.json()
        return None
    except requests.exceptions.RequestException:
        return None


def sum_metric_for_dag(metrics, navn, dag):
    for metric in metrics:
        if metric["name"] == navn:
            total = 0
            for punkt in metric["data"]:
                punkt_dato = datetime.fromisoformat(punkt["date"]).date()
                if punkt_dato == dag:
                    total += punkt["qty"]
            return total
    return 0


def vis_trening():
    st.header("⌚ Aktivitet i går")

    treningsdata = hent_siste_treningsdata()
    i_gaar = date.today() - timedelta(days=1)

    if treningsdata is None:
        st.write("Ingen treningsdata mottatt ennå")
    else:
        metrics = treningsdata["data"]["metrics"]

        steg = sum_metric_for_dag(metrics, "step_count", i_gaar)
        bevegelse = sum_metric_for_dag(metrics, "active_energy", i_gaar)
        trening = sum_metric_for_dag(metrics, "apple_exercise_time", i_gaar)
        oppreist = sum_metric_for_dag(metrics, "apple_stand_hour", i_gaar)

        col1, col2 = st.columns(2)
        col1.metric("👟 Skritt", f"{steg:,.0f}".replace(",", " "))
        col2.metric("🔴 Bevegelse", f"{bevegelse:.0f} kJ")

        col3, col4 = st.columns(2)
        col3.metric("🟢 Trening", f"{trening:.0f} min")
        col4.metric("🔵 Oppreist", f"{oppreist:.0f} timer")