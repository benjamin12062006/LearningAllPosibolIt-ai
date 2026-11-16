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

NEST_REJECTIONS: Final = frozenset({400, 403, 404, 409})
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

        if response.status_code in NEST_REJECTIONS:
            raise OperationFailedError(_rejection_message(response))
        if response.status_code == 204:
            return None
        if not response.is_success:
            raise OperationFailedError(UNAVAILABLE)
        try:
            return _JSON_VALUE.validate_json(response.content)
        except ValidationError:
            raise OperationFailedError(UNAVAILABLE) from None


def _rejection_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return UNAVAILABLE
    if isinstance(body, dict) and isinstance(message := body.get("message"), dict):
        message_es = message.get("es")
        if isinstance(message_es, str) and message_es.strip():
            return message_es
    return UNAVAILABLE
