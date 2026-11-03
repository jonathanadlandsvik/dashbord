"""Regnestykkene for vanene. Ren logikk, slik at reglene kan testes uten nettside.

Begreper:
- En vane *gjelder* en dag hvis den er aktiv da og dagen er en av ukedagene dens.
- Ukemålet vurderes mot dagene vanen gjelder i uka. Starter en vane midt i en
  uke, blir målet den uka aldri høyere enn antall dager som er igjen.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlmodel import Session, col, select

from app.models import Avkrysning, Ukeoppsummering, Vane

SKJERMTID_MAL = Decimal("2.5")  # timer per dag, i snitt over uka
ANTALL_UKER_HISTORIKK = 8


class Tilstand(StrEnum):
    NADD = "nådd"
    MULIG = "mulig"
    IKKE_NADD = "ikke nådd"


@dataclass(frozen=True)
class Ukestatus:
    vane: Vane
    antall: int
    mal: int
    tilstand: Tilstand
    dager: list[tuple[date, bool | None]]  # True = gjort, False = ikke gjort, None = gjelder ikke


@dataclass(frozen=True)
class Uke:
    start: date
    prosent: int | None  # andel av ukemålene som ble nådd, None hvis ingen vaner gjaldt
    skjermtid: Decimal | None


def uke_start(dag: date) -> date:
    return dag - timedelta(days=dag.weekday())


def ukedager(start: date) -> list[date]:
    return [start + timedelta(days=i) for i in range(7)]


def er_aktiv(vane: Vane, dag: date) -> bool:
    return vane.aktiv_fra <= dag and (vane.aktiv_til is None or dag < vane.aktiv_til)


def gjelder(vane: Vane, dag: date) -> bool:
    return er_aktiv(vane, dag) and dag.weekday() in vane.ukedager


def vaner_i_perioden(db: Session, fra: date, til: date) -> list[Vane]:
    """Alle vaneversjoner som var aktive en eller annen dag i [fra, til]."""
    return list(
        db.exec(
            select(Vane)
            .where(Vane.aktiv_fra <= til)
            .where((col(Vane.aktiv_til).is_(None)) | (col(Vane.aktiv_til) > fra))
            .order_by(Vane.sortering, Vane.aktiv_fra)
        ).all()
    )


def vaner_for_dag(db: Session, dag: date) -> list[Vane]:
    return [v for v in vaner_i_perioden(db, dag, dag) if gjelder(v, dag)]


def avkryssede(db: Session, fra: date, til: date) -> set[tuple[int, date]]:
    rader = db.exec(
        select(Avkrysning.vane_id, Avkrysning.dato)
        .where(Avkrysning.dato >= fra)
        .where(Avkrysning.dato <= til)
    ).all()
    return {(vane_id, dato) for vane_id, dato in rader}


def ukestatus(vane: Vane, start: date, gjort: set[tuple[int, date]], i_dag: date) -> Ukestatus:
    dager: list[tuple[date, bool | None]] = []
    antall = gjenstar = gjeldende = 0
    for dag in ukedager(start):
        if not gjelder(vane, dag):
            dager.append((dag, None))
            continue
        gjeldende += 1
        er_gjort = (vane.id, dag) in gjort
        dager.append((dag, er_gjort))
        if er_gjort:
            antall += 1
        elif dag >= i_dag:
            gjenstar += 1  # i dag og senere kan fortsatt krysses av

    mal = min(vane.ukemal, gjeldende)
    if antall >= mal:
        tilstand = Tilstand.NADD
    elif antall + gjenstar >= mal:
        tilstand = Tilstand.MULIG
    else:
        tilstand = Tilstand.IKKE_NADD
    return Ukestatus(vane=vane, antall=antall, mal=mal, tilstand=tilstand, dager=dager)


def uke(db: Session, start: date, i_dag: date) -> list[Ukestatus]:
    slutt = start + timedelta(days=6)
    gjort = avkryssede(db, start, slutt)
    statuser = [ukestatus(v, start, gjort, i_dag) for v in vaner_i_perioden(db, start, slutt)]
    return [s for s in statuser if s.mal > 0]


def andel_nadd(statuser: Iterable[Ukestatus]) -> int | None:
    """Prosent av ukemålene som ble nådd. Mer enn målet teller ikke ekstra."""
    statuser = list(statuser)
    total = sum(s.mal for s in statuser)
    if total == 0:
        return None
    return round(100 * sum(min(s.antall, s.mal) for s in statuser) / total)


def historikk(db: Session, i_dag: date, antall: int = ANTALL_UKER_HISTORIKK) -> list[Uke]:
    denne = uke_start(i_dag)
    starter = [denne - timedelta(weeks=i) for i in range(antall - 1, -1, -1)]
    skjermtid = {
        u.uke_start: u.skjermtid_timer
        for u in db.exec(
            select(Ukeoppsummering).where(col(Ukeoppsummering.uke_start).in_(starter))
        ).all()
    }
    uker = [
        Uke(start=s, prosent=andel_nadd(uke(db, s, i_dag)), skjermtid=skjermtid.get(s))
        for s in starter
    ]
    # Tomme uker fra før vanene fantes er bare støy.
    while uker and uker[0].prosent is None and uker[0].skjermtid is None:
        uker.pop(0)
    return uker


def kryss_av(db: Session, vane: Vane, dag: date) -> bool:
    """Snur avkrysningen. Returnerer True hvis vanen nå er krysset av."""
    eksisterende = db.get(Avkrysning, (vane.id, dag))
    if eksisterende is not None:
        db.delete(eksisterende)
        db.commit()
        return False
    db.add(Avkrysning(vane_id=vane.id, dato=dag))
    db.commit()
    return True
