import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo
from styling import last_css
from vaer import vis_vaer
from bysykkel import vis_bysykkel
from kalender import vis_kalender
from trening import vis_trening

st.set_page_config(page_title="Mitt dashbord", page_icon="📋", layout="centered")

last_css()

st.title("God morgen!")
oslo = ZoneInfo("Europe/Oslo")
naa = datetime.now(oslo)
st.caption(naa.strftime("%A %d. %B %Y, kl %H:%M") + f" • uke {naa.isocalendar().week}")

st.divider()

vis_vaer()
vis_bysykkel()
vis_kalender()
vis_trening()