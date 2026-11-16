"""Arranque del servidor MCP por `stdio` (`uv run ktsu-mcp`, E6.7).

Lo lanza el cliente MCP (Claude Code, Codex…) como subproceso. Los mensajes MCP
van por `stdout`; el diagnóstico, por `stderr`. La configuración llega por el
entorno y nunca se imprime.
"""

import asyncio
import logging
import sys

import httpx
from mcp.server.stdio import stdio_server
from pydantic import Field, HttpUrl, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ktsu_ai.config.configuration import MIN_SERVICE_TOKEN_LENGTH
from ktsu_ai.infrastructure.integration_infrastructure.nest_integration_gateway import (
    NestIntegrationGateway,
)
from ktsu_ai.mcp_server.server import build_mcp_server

REQUEST_TIMEOUT_SECONDS = 30.0


class McpGatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KTSU_", extra="ignore")

    nest_url: HttpUrl
    # El mismo valor que `MCP_ADAPTER_SERVICE_TOKEN` en Nest.
    mcp_adapter_token: SecretStr = Field(min_length=MIN_SERVICE_TOKEN_LENGTH)

    @field_validator("nest_url")
    @classmethod
    def _validate_nest_url(cls, url: HttpUrl) -> HttpUrl:
        is_loopback = url.host in {"127.0.0.1", "localhost", "[::1]"}
        if url.scheme == "http" and not is_loopback:
            raise ValueError("HTTP solo está disponible en loopback.")
        if url.username or url.password or url.query or url.fragment or url.path != "/":
            raise ValueError("Usa la URL base de Nest, sin credenciales ni ruta.")
        return url


class McpSettings(McpGatewaySettings):
    mcp_credential: SecretStr = Field(min_length=16)


async def serve(settings: McpSettings) -> None:
    async with httpx.AsyncClient(
        base_url=str(settings.nest_url),
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        gateway = NestIntegrationGateway(
            client,
            settings.mcp_adapter_token.get_secret_value(),
            settings.mcp_credential.get_secret_value(),
        )
        server = build_mcp_server(gateway)
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    try:
        settings = McpSettings()
    except ValidationError as error:
        # Solo los nombres de las variables: los valores pueden ser secretos.
        missing = ", ".join(
            "KTSU_" + str(item["loc"][0]).upper() for item in error.errors()
        )
        print(f"Configuración MCP incompleta o inválida: {missing}", file=sys.stderr)
        raise SystemExit(2) from None
    asyncio.run(serve(settings))


if __name__ == "__main__":
    main()
