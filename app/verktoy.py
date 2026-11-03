"""Små verktøy som kjøres fra terminalen, ikke fra nettsiden.

    uv run python -m app.verktoy ny-nokkel --navn iPhone
    uv run python -m app.verktoy nokler
    uv run python -m app.verktoy tilbakekall --navn iPhone
    uv run python -m app.verktoy importer-helsedata helsedata.db

Bruker DATABASE_URL_UNPOOLED (direkte adresse), som migrasjonene. Mot production
settes den foran kommandoen, se README.
"""

import argparse
import secrets
import sqlite3
import sys
from datetime import date

from sqlalchemy import Engine, create_engine, pool
from sqlmodel import Session, select

from app.auth import hash_token, naa
from app.config import hent_settings
from app.db import PSYCOPG_ARGS, til_sqlalchemy_url
from app.helsedata import Helsedata, lagre
from app.models import IngestNokkel

NOKKEL_PREFIKS = "dsh_"  # gjør nøkkelen lett å kjenne igjen, f.eks. i hemmelighetsskannere


def _engine() -> Engine:
    settings = hent_settings()
    url = settings.database_url_unpooled or settings.database_url
    if url is None:
        sys.exit("Fant verken DATABASE_URL_UNPOOLED eller DATABASE_URL.")
    return create_engine(
        til_sqlalchemy_url(url.get_secret_value()),
        poolclass=pool.NullPool,
        connect_args=PSYCOPG_ARGS,
    )


def ny_nokkel(db: Session, navn: str) -> str:
    if db.exec(select(IngestNokkel).where(IngestNokkel.navn == navn)).first():
        raise ValueError(f"Det finnes allerede en nøkkel som heter «{navn}».")
    nokkel = NOKKEL_PREFIKS + secrets.token_urlsafe(32)
    db.add(IngestNokkel(navn=navn, nokkel_hash=hash_token(nokkel)))
    db.commit()
    return nokkel


def tilbakekall(db: Session, navn: str) -> None:
    rad = db.exec(select(IngestNokkel).where(IngestNokkel.navn == navn)).first()
    if rad is None:
        raise ValueError(f"Fant ingen nøkkel som heter «{navn}».")
    rad.tilbakekalt = naa()
    db.add(rad)
    db.commit()


def importer_helsedata(db: Session, sti: str) -> int:
    """Leser tabellen dagsaktivitet fra v1-mottakerens SQLite-fil."""
    with sqlite3.connect(f"file:{sti}?mode=ro", uri=True) as kilde:
        kilde.row_factory = sqlite3.Row
        kolonner = {r["name"] for r in kilde.execute("PRAGMA table_info(dagsaktivitet)")}
        felt = [
            f
            for f in ("skritt", "aktiv_energi", "treningsminutter", "oppreist_minutter")
            if f in kolonner
        ]
        rader = kilde.execute(f"SELECT dato, {', '.join(felt)} FROM dagsaktivitet").fetchall()  # noqa: S608 (feltnavnene kommer fra listen over, ikke fra brukeren)
    for rad in rader:
        data = Helsedata(dato=date.fromisoformat(rad["dato"]), **{f: rad[f] for f in felt})
        lagre(db, data, kilde="v1-import")
    return len(rader)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.verktoy")
    under = parser.add_subparsers(dest="kommando", required=True)
    p = under.add_parser("ny-nokkel", help="lag en ny API-nøkkel for snarveien")
    p.add_argument("--navn", required=True)
    under.add_parser("nokler", help="vis nøklene (uten selve nøkkelen)")
    p = under.add_parser("tilbakekall", help="slå av en nøkkel")
    p.add_argument("--navn", required=True)
    p = under.add_parser("importer-helsedata", help="importer helsedata.db fra v1")
    p.add_argument("fil")
    args = parser.parse_args(argv)

    with Session(_engine()) as db:
        try:
            if args.kommando == "ny-nokkel":
                nokkel = ny_nokkel(db, args.navn)
                # Nøkkelen alene på stdout, så den kan sendes rett til pbcopy.
                print(
                    "Nøkkelen vises bare denne ene gangen. Den lagres bare som hash.",
                    file=sys.stderr,
                )
                print(nokkel)
            elif args.kommando == "nokler":
                for n in db.exec(select(IngestNokkel).order_by(IngestNokkel.opprettet)).all():
                    status = "tilbakekalt" if n.tilbakekalt else "aktiv"
                    brukt = n.sist_brukt.strftime("%Y-%m-%d %H:%M") if n.sist_brukt else "aldri"
                    print(f"{n.navn:20} {status:12} sist brukt: {brukt}")
            elif args.kommando == "tilbakekall":
                tilbakekall(db, args.navn)
                print(f"«{args.navn}» er tilbakekalt.")
            elif args.kommando == "importer-helsedata":
                antall = importer_helsedata(db, args.fil)
                print(f"Importerte {antall} dager.")
        except ValueError as feil:
            sys.exit(str(feil))


if __name__ == "__main__":
    main()
