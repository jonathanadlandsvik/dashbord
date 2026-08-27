# 📋 Hverdagsdashbord

Et personlig dashbord bygget i Python og Streamlit som samler vær, bysykkeltilgjengelighet, kalenderavtaler og treningsdata fra Apple Watch på ett sted.

## Funksjonalitet

- **☀️ Vær** – henter time-for-time temperatur og nedbør fra Yr (MET Norway sitt API), visualisert med interaktive grafer
- **🚲 Bysykkel** – viser sanntids tilgjengelighet av vanlige sykler og el-sykler på valgt stativ (GBFS-standarden)
- **📅 Kalender** – henter dagens hendelser fra alle Google-kalendere brukeren abonnerer på, med korrekt tidssone-håndtering
- **⌚ Aktivitet** – viser skritt, aktiv energi, treningstid og oppreist-timer fra Apple Watch, automatisk eksportert via Health Auto Export

## Arkitektur

Prosjektet består av tre deler:

1. **Dashbord** (denne repoen) – Streamlit-applikasjon som henter og viser data fra alle kilder, deployet på Streamlit Community Cloud
2. **Mottaker-API** – en separat Flask-applikasjon hostet på PythonAnywhere som tar imot treningsdata fra iPhone daglig og lagrer den i en SQLite-database
3. **Datakilder** – Yr og GBFS (åpne API-er), Google Calendar API (OAuth-autentisert), og Health Auto Export (iOS-app som eksporterer HealthKit-data)


## Teknologier

- **Python** – Streamlit, Pandas, Altair, Flask, Requests
- **API-er** – Yr/MET Norway, GBFS (Trondheim Bysykkel), Google Calendar API, egen REST API
- **Lagring** – SQLite
- **Deployment** – Streamlit Community Cloud, PythonAnywhere
- **Versjonskontroll** – Git/GitHub
  

## Bakgrunn

Prosjektet startet som en måte å lære Python-utvikling, API-integrasjon og skydeployment i praksis, samtidig som det løser et reelt behov: én rask oversikt over dagen før jeg går ut døra.
