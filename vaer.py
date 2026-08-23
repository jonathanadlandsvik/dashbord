import streamlit as st
import pandas as pd
import altair as alt
import requests
from datetime import datetime, date


def vis_vaer():
    st.header("☀️ Vær i dag")

    lat, lon = 63.4305, 10.3951

    headers = {"User-Agent": "Hverdagsdashbord/1.0 jonathan.adlandsvik@gmail.com"}
    url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"

    response = requests.get(url, headers=headers)
    data = response.json()

    today = date.today()

    timer = []
    temperaturer = []
    nedbor = []

    for punkt in data["properties"]["timeseries"]:
        tidspunkt = datetime.fromisoformat(punkt["time"].replace("Z", "+00:00"))

        if tidspunkt.date() == today:
            timer.append(tidspunkt.strftime("%H:%M"))
            temperaturer.append(punkt["data"]["instant"]["details"]["air_temperature"])

            if "next_1_hours" in punkt["data"]:
                nedbor.append(punkt["data"]["next_1_hours"]["details"]["precipitation_amount"])
            else:
                nedbor.append(0)

    vaerdata = pd.DataFrame({
        "Temperatur (°C)": temperaturer,
        "Nedbør (mm)": nedbor
    }, index=timer)

    vaerdata_reset = vaerdata.reset_index().rename(columns={"index": "Klokkeslett"})

    temp_graf = alt.Chart(vaerdata_reset).mark_line(point=True).encode(
        x=alt.X("Klokkeslett", sort=None, axis=alt.Axis(labelAngle=0)),
        y="Temperatur (°C)"
    )
    st.altair_chart(temp_graf, use_container_width=True)

    nedbor_graf = alt.Chart(vaerdata_reset).mark_bar().encode(
        x=alt.X("Klokkeslett", sort=None, axis=alt.Axis(labelAngle=0)),
        y="Nedbør (mm)"
    )
    st.altair_chart(nedbor_graf, use_container_width=True)