"""Solo la API Nest puede llamar a `/v1/…` (plan 01, S7).

Nest manda `Authorization: Bearer <AI_SERVICE_TOKEN>`. Se compara con
`hmac.compare_digest`, que tarda lo mismo acierte o falle: así no se puede
adivinar el token midiendo cuánto tarda la respuesta.
"""

import hmac
from typing import Annotated, Final

from fastapi import Header
from pydantic import SecretStr

from ktsu_ai.common.error import AppError, ErrorCode

BEARER_PREFIX: Final = "Bearer "


class InternalAuth:
    """Dependencia de FastAPI: `Depends(internal_auth)` en las rutas privadas."""

    def __init__(self, service_token: SecretStr) -> None:
        self._expected = service_token.get_secret_value().encode()

    async def __call__(
        self,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        if not self._is_valid(authorization):
            raise AppError(ErrorCode.AUTH_SERVICE_TOKEN_INVALID)

    def _is_valid(self, authorization: str | None) -> bool:
        if authorization is None or not authorization.startswith(BEARER_PREFIX):
            return False
        presented = authorization.removeprefix(BEARER_PREFIX).encode()
        return hmac.compare_digest(presented, self._expected)
