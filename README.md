# Hverdagsdashbord

Et personlig dashbord for mobilen. Om morgenen viser det vær, bysykler, dagens avtaler og
gårsdagens aktivitet fra Apple Watch. Om kvelden krysser jeg av daglige vaner.

Bygd med FastAPI, HTMX og Postgres (Neon), og kjører på Vercel. Innlogging med passkeys.
Den første versjonen, i Streamlit, ligger i taggen
[`v1-streamlit`](https://github.com/jonathanadlandsvik/dashbord/tree/v1-streamlit).

## Kjøre lokalt

Krever [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env                      # fyll inn verdiene
uv run alembic upgrade head
uv run uvicorn app.main:app --reload      # http://localhost:8000
```

## Tester

```bash
uv run ruff check .
uv run pytest                             # databasetestene trenger TEST_DATABASE_URL
```

`TEST_DATABASE_URL` skal peke på en tom Postgres, aldri på Neon: testene sletter tabellene.
GitHub Actions kjører alt på hver push.

## Drift

```bash
# Migrasjoner mot production
DATABASE_URL_UNPOOLED="$(npx neon@latest connection-string production)" uv run alembic upgrade head

# API-nøkkel for iPhone-snarveien
uv run python -m app.verktoy ny-nokkel --navn iPhone

# Nytt Google-token hvis kalenderen slutter å virke
uv run --with google-auth-oauthlib python scripts/hent_google_token.py
```

Se [PRIVACY.md](PRIVACY.md) for hvilke data appen lagrer.
