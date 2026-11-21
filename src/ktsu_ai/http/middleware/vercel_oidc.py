"""Guarda el token OIDC que Vercel añade a cada petición (deploys, bitácora 07).

Middleware ASGI puro: no toca el cuerpo, así que no interfiere con respuestas
en streaming. Quién usa el token lo decide `bootstrap`.
"""

from collections.abc import Callable
from typing import Final

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

VERCEL_OIDC_HEADER: Final = "x-vercel-oidc-token"


class RememberVercelOidcToken:
    def __init__(self, app: ASGIApp, remember: Callable[[str], None]) -> None:
        self._app = app
        self._remember = remember

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            token = Headers(scope=scope).get(VERCEL_OIDC_HEADER)
            if token:
                self._remember(token)
        await self._app(scope, receive, send)
