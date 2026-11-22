"""Pasarela HTTP de integraciones de Nest para el servidor MCP (E6.7).

Cada petición lleva dos credenciales: el token del adaptador (quién es este
proceso) y la credencial delegada de la persona (para quién actúa). Nest valida
las dos en cada llamada; aquí no se reintenta ni se guarda nada.
"""

from typing import Final, Literal
from urllib.parse import quote
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from ktsu_ai.application.integration_ports.out_integration_gateway import (
    IntegrationOperation,
    IntegrationRejectedError,
)
from ktsu_ai.domain.agent.agent_run import JsonObject, JsonValue

BASE_PATH: Final = "/internal/v1/mcp-integrations"
# Nest responde con un mensaje público en estos casos; el resto es un fallo.
NEST_REJECTIONS: Final = frozenset({400, 401, 403, 404, 409, 413, 422, 429})
UNAVAILABLE: Final = "No se pudo completar la operación en KTSU."
# El catálogo de lectura y propuestas tiene 67 operaciones.
MAX_OPERATIONS: Final = 128
_JSON_VALUE = TypeAdapter(JsonValue)


class _OperationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    description: str = Field(min_length=1, max_length=2000)
    input_schema: JsonObject = Field(alias="inputSchema")
    level: Literal["read", "write"]


class _CatalogPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    operations: list[_OperationPayload] = Field(max_length=MAX_OPERATIONS)


class NestIntegrationGateway:
    def __init__(
        self,
        client: httpx.AsyncClient,
        adapter_token: str,
        credential: str,
        *,
        oauth: bool = False,
    ) -> None:
        self._client = client
        credential_header = "X-Ktsu-Mcp-OAuth" if oauth else "X-Ktsu-Delegation"
        self._headers = {
            "Authorization": f"Bearer {adapter_token}",
            credential_header: f"Bearer {credential}",
        }

    async def session(self) -> None:
        await self._request("GET", f"{BASE_PATH}/session")

    async def operations(self) -> tuple[IntegrationOperation, ...]:
        response = await self._request("GET", f"{BASE_PATH}/operations")
        try:
            catalog = _CatalogPayload.model_validate_json(response.content)
        except ValidationError:
            raise IntegrationRejectedError(UNAVAILABLE) from None
        return tuple(
            IntegrationOperation(
                name=operation.name,
                description=operation.description,
                input_schema=operation.input_schema,
                level=operation.level,
            )
            for operation in catalog.operations
        )

    async def call(
        self, operation: IntegrationOperation, arguments: JsonObject
    ) -> JsonValue:
        name = quote(operation.name, safe="")
        mode = "execute" if operation.level == "read" else "prepare"
        response = await self._request(
            "POST",
            f"{BASE_PATH}/operations/{name}",
            {"callId": str(uuid4()), "mode": mode, "arguments": arguments},
        )
        if response.status_code == 204:
            return None
        try:
            return _JSON_VALUE.validate_json(response.content)
        except ValidationError:
            raise IntegrationRejectedError(UNAVAILABLE) from None

    async def _request(
        self, method: str, path: str, body: JsonObject | None = None
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method, path, headers=self._headers, json=body
            )
        except (httpx.RequestError, ValueError):
            raise IntegrationRejectedError(UNAVAILABLE) from None
        if response.status_code in NEST_REJECTIONS:
            message, code = _rejection(response)
            raise IntegrationRejectedError(message, response.status_code, code)
        if not response.is_success:
            raise IntegrationRejectedError(UNAVAILABLE)
        return response


def _rejection(response: httpx.Response) -> tuple[str, str | None]:
    try:
        body = response.json()
    except ValueError:
        return UNAVAILABLE, None
    if isinstance(body, dict) and isinstance(message := body.get("message"), dict):
        message_es = message.get("es")
        if isinstance(message_es, str) and message_es.strip():
            code = body.get("code")
            return message_es, code if isinstance(code, str) else None
    return UNAVAILABLE, None
