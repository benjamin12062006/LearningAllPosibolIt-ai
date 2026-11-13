"""Identificador de petición y una línea de registro por petición (plan 01, S8).

Se respeta el `X-Request-Id` que manda Nest si tiene una forma segura: así una
misma petición se sigue en los registros de los dos servicios. No se registran
tokens, cuerpos ni query strings.
"""

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Final

from fastapi import Request, Response

REQUEST_ID_HEADER: Final = "X-Request-Id"

# El mismo patrón que la API Nest (`src/common/http/request-id.ts`).
REQUEST_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

logger = logging.getLogger("ktsu_ai.http")

type CallNext = Callable[[Request], Awaitable[Response]]


async def observe_request(request: Request, call_next: CallNext) -> Response:
    request.state.request_id = _request_id_of(request)
    started = time.perf_counter()

    response = await call_next(request)

    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    _log_request(request, response.status_code, time.perf_counter() - started)
    return response


def request_id_of(request: Request) -> str:
    """El identificador ya asignado; si el middleware no corrió, uno nuevo."""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id
    return str(uuid.uuid4())


def _request_id_of(request: Request) -> str:
    incoming = request.headers.get(REQUEST_ID_HEADER)
    if incoming is not None and REQUEST_ID_PATTERN.match(incoming):
        return incoming
    return str(uuid.uuid4())


def _log_request(request: Request, status: int, elapsed_seconds: float) -> None:
    level = _level_for(status)
    logger.log(
        level,
        "HTTP %s %s %d %.1fms request_id=%s",
        request.method,
        request.url.path,
        status,
        elapsed_seconds * 1000,
        request.state.request_id,
    )


def _level_for(status: int) -> int:
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO
