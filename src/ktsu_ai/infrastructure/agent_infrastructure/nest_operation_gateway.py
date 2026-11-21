"""Pasarela HTTP del contrato E6.3a, sin reintentar operaciones."""

from typing import Final, Literal
from urllib.parse import quote

import httpx
from pydantic import TypeAdapter, ValidationError

from ktsu_ai.application.agent_ports.out_operation_gateway import (
    OperationFailedError,
    Preparation,
)
from ktsu_ai.domain.agent.agent_run import JsonObject, JsonValue, RunIdentity

UNAVAILABLE: Final = "No se pudo completar la operación en Nest."
INVALID_PREPARATION: Final = "Nest no devolvió un resumen válido para confirmar."
MAX_CONFIRMATION_LENGTH: Final = 16_000
_JSON_VALUE = TypeAdapter(JsonValue)


class NestOperationGateway:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def execute(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> JsonValue:
        return await self._send(identity, operation, "execute", arguments)

    async def prepare(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> Preparation:
        response = await self._send(identity, operation, "prepare", arguments)
        summary = response.get("summary") if isinstance(response, dict) else None
        if (
            not isinstance(summary, str)
            or not 0 < len(summary.strip()) <= MAX_CONFIRMATION_LENGTH
        ):
            raise OperationFailedError(INVALID_PREPARATION)
        if isinstance(response, dict) and response.get("status") == "confirmed":
            return Preparation(summary.strip(), True, response.get("result"))
        return Preparation(summary.strip())

    async def _send(
        self,
        identity: RunIdentity,
        operation: str,
        mode: Literal["execute", "prepare"],
        arguments: JsonObject,
    ) -> JsonValue:
        run_id = quote(identity.run_id, safe="")
        name = quote(operation, safe="")
        path = f"/internal/v1/agent-runs/{run_id}/operations/{name}"
        try:
            response = await self._client.post(
                path,
                headers={"Authorization": f"Bearer {identity.credential}"},
                json={"mode": mode, "arguments": arguments},
            )
        except (httpx.RequestError, ValueError):
            raise OperationFailedError(UNAVAILABLE) from None

        if _is_nest_rejection(response.status_code):
            raise _rejection(response)
        if response.status_code == 204:
            return None
        if not response.is_success:
            raise OperationFailedError(UNAVAILABLE)
        try:
            return _JSON_VALUE.validate_json(response.content)
        except ValidationError:
            raise OperationFailedError(UNAVAILABLE) from None


def _is_nest_rejection(status: int) -> bool:
    """Un 4xx con mensaje público. El 401 es de la credencial de la ejecución, no del modelo."""
    return 400 <= status < 500 and status != 401


def _rejection(response: httpx.Response) -> OperationFailedError:
    try:
        body = response.json()
    except ValueError:
        return OperationFailedError(UNAVAILABLE)
    if not isinstance(body, dict):
        return OperationFailedError(UNAVAILABLE)
    message = body.get("message")
    spanish = _text_in(message, "es")
    if spanish is None:
        return OperationFailedError(UNAVAILABLE)
    code = body.get("code")
    return OperationFailedError(
        spanish,
        code if isinstance(code, str) and code else None,
        _text_in(message, "en"),
    )


def _text_in(message: JsonValue, language: str) -> str | None:
    if not isinstance(message, dict):
        return None
    text = message.get(language)
    if isinstance(text, str) and text.strip():
        return text
    return None
