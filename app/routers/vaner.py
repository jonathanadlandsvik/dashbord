"""Vanesidene: kryss av for dagen, se uka, skriv ukeoppsummering og se historikk."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app import vaner
from app.auth import DbSesjon, Innlogget, InnloggetMedCsrf, Ugyldig, csrf_token
from app.helsedata import tolk_tall
from app.models import Ukeoppsummering, Vane
from app.templating import templates
from app.tid import naa

router = APIRouter(prefix="/vaner")

REDIGERBARE_DAGER = 7  # glemte du å krysse av, kan du rette opptil en uke tilbake


def _gyldig_dag(dag: date, i_dag: date) -> bool:
    return i_dag - timedelta(days=REDIGERBARE_DAGER) <= dag <= i_dag


def _dagens(db, dag: date) -> dict:
    liste = vaner.vaner_for_dag(db, dag)
    gjort = vaner.avkryssede(db, dag, dag)
    return {
        "vaner": liste,
        "gjort": gjort,
        "antall": sum(1 for v in liste if (v.id, dag) in gjort),
    }


def _ukekontekst(db, dag: date, i_dag: date) -> dict:
    start = vaner.uke_start(dag)
    return {"uke": vaner.uke(db, start, i_dag), "ukestart": start, "i_dag": i_dag}


def _oppsummering(db, start: date) -> dict:
    return {
        "ukestart": start,
        "oppsummering": db.get(Ukeoppsummering, start),
        "skjermtid_mal": vaner.SKJERMTID_MAL,
    }


@router.get("", response_class=HTMLResponse)
def side(
    request: Request,
    sesjon: Innlogget,
    db: DbSesjon,
    dato: Annotated[date | None, Query()] = None,
) -> Response:
    i_dag = naa().date()
    dag = dato or i_dag
    if not _gyldig_dag(dag, i_dag):
        return RedirectResponse("/vaner", status_code=303)
    return templates.TemplateResponse(
        request,
        "vaner.html",
        {
            "csrf": csrf_token(request, sesjon),
            "dag": dag,
            "forrige": dag - timedelta(days=1)
            if _gyldig_dag(dag - timedelta(days=1), i_dag)
            else None,
            "neste": dag + timedelta(days=1) if dag < i_dag else None,
            **_dagens(db, dag),
            "historikk": vaner.historikk(db, i_dag),
            "skjermtid_mal": vaner.SKJERMTID_MAL,
            **_ukekontekst(db, dag, i_dag),
            **_oppsummering(db, vaner.uke_start(dag)),
        },
    )


@router.post("/kryss", response_class=HTMLResponse)
def kryss(
    request: Request,
    _: InnloggetMedCsrf,
    db: DbSesjon,
    vane_id: Annotated[int, Form()],
    dato: Annotated[date, Form()],
) -> HTMLResponse:
    i_dag = naa().date()
    vane = db.get(Vane, vane_id)
    if not _gyldig_dag(dato, i_dag) or vane is None or not vaner.gjelder(vane, dato):
        raise Ugyldig("Denne vanen kan ikke krysses av for den dagen.")
    vaner.kryss_av(db, vane, dato)
    return templates.TemplateResponse(
        request,
        "vaner/kryss_svar.html",
        {"v": vane, "dag": dato, **_dagens(db, dato), **_ukekontekst(db, dato, i_dag)},
    )


@router.post("/uke/{start}", response_class=HTMLResponse)
def lagre_oppsummering(
    request: Request,
    _: InnloggetMedCsrf,
    db: DbSesjon,
    start: date,
    skjermtid: Annotated[str, Form(max_length=10)] = "",
    refleksjon: Annotated[str, Form(max_length=500)] = "",
) -> HTMLResponse:
    if start.weekday() != 0 or start > vaner.uke_start(naa().date()):
        raise Ugyldig("Ugyldig uke.")
    kontekst = _oppsummering(db, start)
    try:
        timer = tolk_tall(skjermtid)
    except ValueError:
        timer = -1
    if timer is not None and not 0 <= timer <= 24:
        return templates.TemplateResponse(
            request,
            "vaner/oppsummering.html",
            {
                **kontekst,
                "feil": "Skjermtid må være et tall mellom 0 og 24 timer.",
                "verdier": {"skjermtid": skjermtid, "refleksjon": refleksjon},
            },
        )
    db.merge(
        Ukeoppsummering(
            uke_start=start,
            skjermtid_timer=(
                None
                if timer is None
                else Decimal(str(timer)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            ),
            refleksjon=refleksjon.strip() or None,
            oppdatert=naa(),
        )
    )
    db.commit()
    return templates.TemplateResponse(
        request, "vaner/oppsummering.html", {**_oppsummering(db, start), "lagret": True}
    )
