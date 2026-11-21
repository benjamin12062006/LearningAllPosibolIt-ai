"""Servidor MCP por Streamable HTTP. Descope emite los tokens y Nest los valida."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Self

import httpx
import uvicorn
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from pydantic import Field, HttpUrl, SecretStr, model_validator
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from ktsu_ai.application.integration_ports.out_integration_gateway import (
    IntegrationRejectedError,
)
from ktsu_ai.bootstrap.mcp import REQUEST_TIMEOUT_SECONDS, McpGatewaySettings
from ktsu_ai.infrastructure.integration_infrastructure.nest_integration_gateway import (
    NestIntegrationGateway,
)
from ktsu_ai.mcp_server.server import build_mcp_server

MCP_PATH = "/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
READ_SCOPE = "ktsu:mcp:read"
MAX_BODY_BYTES = 64 * 1024


class McpHttpSettings(McpGatewaySettings):
    mcp_resource_url: HttpUrl
    mcp_oauth_issuer: HttpUrl
    nest_vercel_bypass_token: SecretStr | None = Field(default=None, min_length=16)

    @model_validator(mode="after")
    def validate_public_urls(self) -> Self:
        for url in (self.mcp_resource_url, self.mcp_oauth_issuer):
            if (
                url.scheme != "https"
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError(
                    "Usa una URL HTTPS sin credenciales, query ni fragmento."
                )
        if self.mcp_resource_url.path != MCP_PATH:
            raise ValueError("La URL pública debe terminar en /mcp.")
        if self.nest_vercel_bypass_token is not None:
            nest_host = self.nest_url.host or ""
            if self.nest_url.scheme != "https" or not nest_host.endswith(".vercel.app"):
                raise ValueError(
                    "La credencial de Vercel requiere un origen HTTPS de Vercel."
                )
        return self


def create_app(
    settings: McpHttpSettings, *, transport: httpx.AsyncBaseTransport | None = None
) -> Starlette:
    request_gateway: ContextVar[NestIntegrationGateway] = ContextVar("request_gateway")
    manager = StreamableHTTPSessionManager(
        build_mcp_server(request_gateway.get),
        stateless=True,
        json_response=True,
        max_request_body_size=MAX_BODY_BYTES,
    )
    resource = str(settings.mcp_resource_url)
    origin = resource.removesuffix(MCP_PATH)
    host = origin.removeprefix("https://")
    metadata_url = origin + METADATA_PATH
    bypass_token = settings.nest_vercel_bypass_token
    # El origen protegido de Nest acepta esta cabecera de servidor además de
    # las credenciales que valida la pasarela con cada llamada MCP.
    nest_headers = (
        {"x-vercel-protection-bypass": bypass_token.get_secret_value()}
        if bypass_token is not None
        else None
    )
    client = httpx.AsyncClient(
        base_url=str(settings.nest_url),
        headers=nest_headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
    )

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with client, manager.run():
            yield

    async def metadata(_: Request) -> Response:
        return JSONResponse(
            {
                "resource": resource,
                "authorization_servers": [str(settings.mcp_oauth_issuer)],
                "scopes_supported": [READ_SCOPE],
                "bearer_methods_supported": ["header"],
            }
        )

    class ProtectedMcp:
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            request = Request(scope)
            if request.headers.get("host") != host or request.headers.get(
                "origin"
            ) not in (None, origin):
                await JSONResponse({"error": "forbidden"}, 403)(scope, receive, send)
                return
            headers = request.headers.getlist("authorization")
            gateway = _oauth_gateway(client, settings, headers)
            if gateway is None:
                await _challenge(metadata_url)(scope, receive, send)
                return
            try:
                await gateway.session()
            except IntegrationRejectedError as error:
                await _rejection(error, metadata_url)(scope, receive, send)
                return
            ctx = request_gateway.set(gateway)
            try:
                await manager.handle_request(scope, receive, send)
            finally:
                request_gateway.reset(ctx)

    return Starlette(
        routes=[Route(METADATA_PATH, metadata), Route(MCP_PATH, ProtectedMcp())],
        lifespan=lifespan,
    )


def _oauth_gateway(
    client: httpx.AsyncClient, settings: McpHttpSettings, headers: list[str]
) -> NestIntegrationGateway | None:
    if len(headers) != 1 or len(headers[0]) > 8192:
        return None
    scheme, _, token = headers[0].partition(" ")
    if scheme.lower() != "bearer" or not token or any(char.isspace() for char in token):
        return None
    return NestIntegrationGateway(
        client, settings.mcp_adapter_token.get_secret_value(), token, oauth=True
    )


def _challenge(metadata_url: str, error: str | None = None) -> Response:
    value = f'Bearer resource_metadata="{metadata_url}", scope="{READ_SCOPE}"'
    status = 401
    if error is not None:
        value += f', error="{error}"'
    if error == "insufficient_scope":
        status = 403
    return JSONResponse(
        {"error": error or "authorization_required"},
        status,
        headers={"WWW-Authenticate": value, "Cache-Control": "no-store"},
    )


def _rejection(error: IntegrationRejectedError, metadata_url: str) -> Response:
    if error.code == "INTEGRATION_ADAPTER_INVALID":
        return JSONResponse(
            {"error": "service_unavailable"}, 503, headers={"Cache-Control": "no-store"}
        )
    if error.status == 401:
        return _challenge(metadata_url, "invalid_token")
    if error.code == "INTEGRATION_OAUTH_SCOPE_REQUIRED":
        return _challenge(metadata_url, "insufficient_scope")
    return JSONResponse(
        {"error": error.code or "service_unavailable", "message": str(error)},
        error.status or 503,
        headers={"Cache-Control": "no-store"},
    )


def create_app_from_environment() -> Starlette:
    try:
        return create_app(McpHttpSettings())
    except ValueError:
        # Pydantic puede incluir el valor recibido, incluidos tokens.
        raise RuntimeError("Configuración del MCP HTTP inválida.") from None


def main() -> None:
    uvicorn.run(
        create_app_from_environment(), host="127.0.0.1", port=8091, access_log=False
    )
