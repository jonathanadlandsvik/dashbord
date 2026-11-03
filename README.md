# Hverdagsdashbord v2

> Under arbeid. Den forrige versjonen (Streamlit + Flask-mottaker) ligger i taggen
> [`v1-streamlit`](https://github.com/jonathanadlandsvik/dashbord/tree/v1-streamlit) og kjører fra `main`
> til v2 tar over.

Ett personlig dashbord for mobilen: vær, bysykkel, kalender og gårsdagens aktivitet om morgenen,
og avkryssing av daglige vaner om kvelden.

## Planlagt arkitektur

- **Backend:** FastAPI og Pydantic
- **Frontend:** servergenerert HTML med Jinja og HTMX, installerbar som PWA
- **Database:** Postgres hos Neon, SQLModel og Alembic
- **Hosting:** Vercel
- **Innlogging:** passkeys (Face ID) og sesjonscookie

## Kom i gang lokalt

Krever [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                   # installerer Python 3.12 og avhengigheter i .venv
cp .env.example .env                      # fyll inn verdiene
uv run alembic upgrade head               # oppdaterer dev-databasen til nyeste versjon
uv run uvicorn app.main:app --reload      # http://localhost:8000
```

## Innlogging

Innloggingen bruker passkeys (Face ID). Appen har én bruker.

1. Første gang: sett `SETUP_TOKEN` (et langt, tilfeldig passord) i miljøvariablene, åpne
   `/oppsett` og registrer Face ID med den koden. Du får ti gjenopprettingskoder, som
   bare vises én gang.
2. Slett `SETUP_TOKEN` etterpå. Den virker uansett ikke etter at første passkey finnes.
3. Nye enheter legges til fra `/oppsett` mens du er innlogget.
4. Mister du telefonen, logger du inn med en gjenopprettingskode og registrerer en ny passkey.

Sikkerhet: sesjoner og koder lagres bare som SHA-256 i databasen, alle skjemaer har
CSRF-token, endrende forespørsler må komme fra appens egen adresse (Origin-sjekk),
og innlogging sperres et kvarter etter ti mislykkede forsøk.

## Helsedata fra iPhone

En snarvei på iPhonen sender gårsdagens tall til `POST /api/helsedata` med en egen
API-nøkkel i headeren `X-API-Key`. Nøkkelen kan bare sende helsedata, og bare en
hash av den lagres.

```json
{"dato": "2026-11-02", "skritt": 8123, "aktiv_energi": "412,5",
 "treningsminutter": 35, "staatimer": 10}
```

Nøkler håndteres fra terminalen:

```bash
uv run python -m app.verktoy ny-nokkel --navn iPhone   # vises én gang
uv run python -m app.verktoy nokler                    # oversikt
uv run python -m app.verktoy tilbakekall --navn iPhone
uv run python -m app.verktoy importer-helsedata helsedata.db   # historikk fra v1
```

## Database og migrasjoner

Tabellene er definert i `app/models.py`, og hver endring får en migrasjon i
`migrations/versions/`. Migrasjoner bruker den direkte adressen
(`DATABASE_URL_UNPOOLED`), appen bruker den pooled (`DATABASE_URL`).

```bash
uv run alembic current                    # hvilken versjon databasen er på
uv run alembic upgrade head               # kjør nye migrasjoner mot dev
uv run alembic revision -m "beskrivelse"  # lag en ny, tom migrasjon
```

Mot production (henter adressen fra Neon uten å vise den):

```bash
DATABASE_URL_UNPOOLED="$(npx neon@latest connection-string production)" uv run alembic upgrade head
```

## Sjekker

Kjøres også i GitHub Actions på hver push.

```bash
uv run ruff format .                      # formaterer koden
uv run ruff check .                       # lint og sikkerhetsregler
uv run pytest                             # tester (databasetestene hoppes over uten TEST_DATABASE_URL)
```

Databasetestene trenger en egen, tom Postgres i `TEST_DATABASE_URL`. I GitHub Actions
startes en Postgres-container automatisk. Pek den aldri på Neon: testene sletter tabellene.

## Struktur

```
app/
  main.py         inngangspunkt (lag_app)
  config.py       miljøvariabler via pydantic-settings
  db.py           tilkobling til Postgres
  models.py       tabellene
  routers/        sidene
  services/       henting av data fra Yr, bysykkel og kalender
  templates/      Jinja-maler
migrations/       Alembic-migrasjoner
public/static/    CSS og HTMX, servert fra Vercels CDN
tests/
```
