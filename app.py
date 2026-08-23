import streamlit as st
from datetime import datetime

from vaer import vis_vaer
from bysykkel import vis_bysykkel
from kalender import vis_kalender
from trening import vis_trening

st.set_page_config(page_title="Mitt dashbord", page_icon="📋", layout="centered")

st.title("📋 God morgen!")
st.caption(datetime.now().strftime("%A %d. %B %Y, kl %H:%M"))

st.divider()

vis_vaer()
vis_bysykkel()
vis_kalender()
vis_trening()