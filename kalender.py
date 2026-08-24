import streamlit as st
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


def vis_kalender():
    st.header("📅 Planer i dag")

    creds = Credentials(
        token=st.secrets["google"]["access_token"],
        refresh_token=st.secrets["google"]["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=st.secrets["google"]["client_id"],
        client_secret=st.secrets["google"]["client_secret"],
        scopes=["https://www.googleapis.com/auth/calendar.readonly"]
    )

    if creds.expired:
        creds.refresh(Request())

    service = build("calendar", "v3", credentials=creds)

    oslo = ZoneInfo("Europe/Oslo")
    now = datetime.now(oslo)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    kalenderliste = service.calendarList().list().execute()

    alle_hendelser = []

    for kalender in kalenderliste["items"]:
        if kalender["summary"] in ["Ukenumre"]:
            continue

        events_result = service.events().list(
            calendarId=kalender["id"],
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        for event in events_result.get("items", []):
            start = event["start"].get("dateTime", event["start"].get("date"))

            if "T" in start:
                sorteringstid = datetime.fromisoformat(start).astimezone(oslo)
            else:
                sorteringstid = datetime.combine(
                    datetime.fromisoformat(start).date(),
                    datetime.min.time(),
                    tzinfo=oslo
                )

            alle_hendelser.append((sorteringstid, event))

    alle_hendelser.sort(key=lambda par: par[0])

    if not alle_hendelser:
        st.info("🎉 Ingen planer i dag")
    else:
        for sorteringstid, event in alle_hendelser:
            start = event["start"].get("dateTime", event["start"].get("date"))
            tid = sorteringstid.strftime("%H:%M") if "T" in start else "Hele dagen"

            st.markdown(f"""
                <div class="event-kort">
                    <div class="event-tid">{tid}</div>
                    <div class="event-navn">{event['summary']}</div>
                </div>
            """, unsafe_allow_html=True)