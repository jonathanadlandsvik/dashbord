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
uv run uvicorn app.main:app --reload      # http://localhost:8000
```

## Sjekker

Kjøres også i GitHub Actions på hver push.

```bash
uv run ruff format .                      # formaterer koden
uv run ruff check .                       # lint og sikkerhetsregler
uv run pytest                             # tester
```

## Struktur

```
app/
  main.py         inngangspunkt (lag_app)
  config.py       miljøvariabler via pydantic-settings
  routers/        sidene
  services/       henting av data fra Yr, bysykkel og kalender
  templates/      Jinja-maler
public/static/    CSS og HTMX, servert fra Vercels CDN
tests/
```
