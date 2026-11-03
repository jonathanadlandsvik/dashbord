from decimal import Decimal
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.tid import MANEDER, UKEDAGER

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def komma(verdi: float | Decimal | None, desimaler: int = 1) -> str:
    """3.25 -> '3,3'. Norsk desimaltegn."""
    if verdi is None:
        return "–"
    return f"{verdi:.{desimaler}f}".replace(".", ",")


def kort_dato(dag) -> str:
    """'mandag 2. nov.'"""
    return f"{UKEDAGER[dag.weekday()]} {dag.day}. {MANEDER[dag.month - 1][:3]}."


templates.env.filters["komma"] = komma
templates.env.filters["kort_dato"] = kort_dato
