"""API for iPhone-snarveien. Ingen cookies, ingen nettleser: autentisering med nøkkel.

Origin-sjekken i sikkerhet.py gjelder ikke /api/, fordi snarveien ikke er en
nettleser. Til gjengjeld godtas bare en gyldig, ikke-tilbakekalt ingest-nøkkel.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlmodel import select

from app.auth import DbSesjon, hash_token, naa
from app.helsedata import Helsedata, forklar, lagre
from app.models import IngestNokkel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MAKS_STORRELSE = 10 * 1024  # 10 kB er mer enn nok for fire tall


def _oppgitt_nokkel(request: Request) -> str | None:
    # X-API-Key brukes av snarveien: iOS kan fjerne Authorization ved videresending.
    if nokkel := request.headers.get("x-api-key", "").strip():
        return nokkel
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return header.removeprefix("Bearer ").strip() or None
    return None


def _avvis(request: Request, grunn: str) -> JSONResponse:
    # Logg hvorfor, men aldri selve nøkkelen.
    logger.warning(
        "Avvist %s %s fra %s: %s",
        request.method,
        request.url.path,
        request.headers.get("x-real-ip") or (request.client.host if request.client else "?"),
        grunn,
    )
    return JSONResponse(
        {"feil": "ugyldig eller manglende API-nøkkel"},
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/helsedata")
async def motta_helsedata(request: Request, db: DbSesjon) -> JSONResponse:
    if int(request.headers.get("content-length") or 0) > MAKS_STORRELSE:
        return JSONResponse({"feil": "forespørselen er for stor"}, status_code=413)

    oppgitt = _oppgitt_nokkel(request)
    if oppgitt is None:
        return _avvis(request, "mangler nøkkel")
    nokkel = db.exec(
        select(IngestNokkel).where(IngestNokkel.nokkel_hash == hash_token(oppgitt))
    ).first()
    if nokkel is None:
        return _avvis(request, f"ukjent nøkkel (lengde {len(oppgitt)})")
    if nokkel.tilbakekalt is not None:
        return _avvis(request, f"tilbakekalt nøkkel «{nokkel.navn}»")

    kropp = await request.body()
    if len(kropp) > MAKS_STORRELSE:
        return JSONResponse({"feil": "forespørselen er for stor"}, status_code=413)
    try:
        data = Helsedata.model_validate_json(kropp)
    except ValidationError as feil:
        return JSONResponse({"feil": forklar(feil)}, status_code=400)

    lagre(db, data)
    nokkel.sist_brukt = naa()
    db.add(nokkel)
    db.commit()
    return JSONResponse({"status": "lagret", "dato": data.dato.isoformat()})
