from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth import Innlogget, csrf_token
from app.templating import templates
from app.tid import hilsen, naa, norsk_dato

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def forside(request: Request, sesjon: Innlogget) -> HTMLResponse:
    tidspunkt = naa()
    return templates.TemplateResponse(
        request,
        "forside.html",
        {
            "hilsen": hilsen(tidspunkt),
            "dato": norsk_dato(tidspunkt),
            "uke": tidspunkt.isocalendar().week,
            "csrf": csrf_token(request, sesjon),
        },
    )
