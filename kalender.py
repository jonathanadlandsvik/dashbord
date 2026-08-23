import streamlit as st
from datetime import datetime, timezone
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

    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_of_day,
        timeMax=end_of_day,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])

    if not events:
        st.write("Ingen planer i dag 🎉")
    else:
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            tid = datetime.fromisoformat(start).strftime("%H:%M") if "T" in start else "Hele dagen"
            st.write(f"**{tid}** – {event['summary']}")