import streamlit as st
import requests


def vis_bysykkel():
    st.header("🚲 Bysykler – S. P. Andersens vei")

    station_id = "293"

    status = requests.get("https://gbfs.urbansharing.com/trondheimbysykkel.no/station_status.json").json()

    for station in status["data"]["stations"]:
        if station["station_id"] == station_id:
            vanlig_sykkel = 0
            el_sykkel = 0

            for vehicle_type in station["vehicle_types_available"]:
                if vehicle_type["vehicle_type_id"] == "bike":
                    vanlig_sykkel = vehicle_type["count"]
                elif vehicle_type["vehicle_type_id"] == "ebike":
                    el_sykkel = vehicle_type["count"]

            col1, col2, col3 = st.columns(3)
            col1.metric("Vanlig sykkel", vanlig_sykkel)
            col2.metric("El-sykkel", el_sykkel)
            col3.metric("Ledige låser", station["num_docks_available"])