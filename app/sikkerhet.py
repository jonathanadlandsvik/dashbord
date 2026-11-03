"""Beskyttelse som gjelder alle forespørsler: sikkerhetsheadere og Origin-sjekk."""

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

TRYGGE_METODER = {"GET", "HEAD", "OPTIONS"}

# Bare egne filer kan lastes. Ingen inline-skript, ingen eval, ingen innbygging i andres sider.
CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


def _origin_fra(url: str) -> str | None:
    deler = urlsplit(url)
    if not deler.scheme or not deler.netloc:
        return None
    return f"{deler.scheme}://{deler.netloc}"


class Sikkerhetsmiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, origin: str, produksjon: bool) -> None:
        super().__init__(app)
        self.origin = origin
        self.produksjon = produksjon

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._fra_eget_nettsted(request):
            svar: Response = PlainTextResponse(
                "Forespørselen kom fra et annet nettsted og ble avvist.", status_code=403
            )
        else:
            svar = await call_next(request)

        svar.headers["Content-Security-Policy"] = CSP
        svar.headers["X-Content-Type-Options"] = "nosniff"
        svar.headers["Referrer-Policy"] = "same-origin"
        svar.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if self.produksjon:
            svar.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return svar

    def _fra_eget_nettsted(self, request: Request) -> bool:
        """Endrende forespørsler må komme fra appens egne sider.

        Nettlesere sender Origin på POST. Mangler den, brukes Referer. API-et for
        iPhone-snarveien (/api/) har ingen nettleser bak seg og bruker nøkkel i stedet.
        """
        if request.method in TRYGGE_METODER or request.url.path.startswith("/api/"):
            return True
        kilde = request.headers.get("origin") or _origin_fra(request.headers.get("referer", ""))
        return kilde == self.origin
