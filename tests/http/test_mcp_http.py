"""Streamable HTTP con un servidor MCP real y una pasarela Nest de prueba."""

import asyncio

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import HttpUrl, SecretStr
from starlette.testclient import TestClient

from ktsu_ai.bootstrap.mcp_http import McpHttpSettings, create_app

RESOURCE = "https://mcp.ktsu.example/mcp"
ISSUER = "https://api.descope.com/v1/apps/agentic/Ptest/MStest"
AUTH = {
    "Authorization": "Bearer access-test",
    "Accept": "application/json, text/event-stream",
}


def test_mcp_http_descubrimiento_catalogo_y_revocacion() -> None:
    revoked = False
    calls = []

    def nest(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Ktsu-Mcp-OAuth"] == "Bearer access-test"
        assert "X-Ktsu-Delegation" not in request.headers
        assert request.headers["Authorization"] == "Bearer " + "a" * 32
        assert request.headers["x-vercel-protection-bypass"] == "protection-test-token"
        route = request.url.path.rsplit("/", 1)[1]
        calls.append(route)
        if revoked:
            return httpx.Response(
                403,
                json={
                    "code": "INTEGRATION_OAUTH_GRANT_REQUIRED",
                    "message": {
                        "es": "Activa el acceso MCP OAuth desde Integraciones."
                    },
                },
            )
        if route == "session":
            return httpx.Response(200, json={})
        if route == "operations":
            return httpx.Response(
                200,
                json={
                    "operations": [
                        {
                            "name": "get_project_overview",
                            "level": "read",
                            "description": "Proyecto permitido",
                            "inputSchema": {
                                "type": "object",
                                "additionalProperties": False,
                            },
                        }
                    ]
                },
            )
        assert route == "get_project_overview"
        return httpx.Response(200, json={"project": "permitido"})

    app = create_app(
        McpHttpSettings(
            nest_url=HttpUrl("https://nest-preview.vercel.app"),
            mcp_adapter_token=SecretStr("a" * 32),
            mcp_resource_url=HttpUrl(RESOURCE),
            mcp_oauth_issuer=HttpUrl(ISSUER),
            nest_vercel_bypass_token=SecretStr("protection-test-token"),
        ),
        transport=httpx.MockTransport(nest),
    )
    with TestClient(app, base_url="https://mcp.ktsu.example") as client:
        metadata = client.get("/.well-known/oauth-protected-resource/mcp")
        assert metadata.json()["authorization_servers"] == [ISSUER]
        assert metadata.json()["resource"] == RESOURCE
        assert metadata.json()["scopes_supported"] == ["ktsu:mcp:read"]
        assert "protection-test-token" not in metadata.text

        request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        absent = client.post("/mcp", json=request)
        assert absent.status_code == 401
        assert (
            'resource_metadata="https://mcp.ktsu.example/.well-known/oauth-protected-resource/mcp"'
            in absent.headers["WWW-Authenticate"]
        )
        origin = client.post(
            "/mcp", json=request, headers={**AUTH, "Origin": "https://other.example"}
        )
        assert origin.status_code == 403
        assert calls == []

        tools = client.post("/mcp", json=request, headers=AUTH)
        assert tools.status_code == 200
        assert [tool["name"] for tool in tools.json()["result"]["tools"]] == [
            "get_project_overview"
        ]
        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_project_overview"},
        }
        result = client.post("/mcp", json=call, headers=AUTH)
        assert result.status_code == 200
        assert result.json()["result"]["structuredContent"] == {"project": "permitido"}
        assert calls[-1] == "get_project_overview"

        revoked = True
        rejected = client.post("/mcp", json=call, headers=AUTH)
        assert rejected.status_code == 403
        assert rejected.json()["error"] == "INTEGRATION_OAUTH_GRANT_REQUIRED"
        assert calls[-1] == "session"


def test_el_sdk_http_mantiene_tokens_separados_entre_clientes() -> None:
    def nest(request: httpx.Request) -> httpx.Response:
        authorization = request.headers["X-Ktsu-Mcp-OAuth"]
        assert "x-vercel-protection-bypass" not in request.headers
        route = request.url.path.rsplit("/", 1)[1]
        if route == "session":
            return httpx.Response(200, json={})
        if route == "operations":
            return httpx.Response(
                200,
                json={
                    "operations": [
                        {
                            "name": "get_project_overview",
                            "level": "read",
                            "description": "Resumen",
                            "inputSchema": {"type": "object"},
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"principal": authorization.split(" ")[1]})

    app = create_app(
        McpHttpSettings(
            nest_url=HttpUrl("http://127.0.0.1:8080"),
            mcp_adapter_token=SecretStr("a" * 32),
            mcp_resource_url=HttpUrl(RESOURCE),
            mcp_oauth_issuer=HttpUrl(ISSUER),
        ),
        transport=httpx.MockTransport(nest),
    )

    async def query(token: str, mode: str) -> str:
        async with (
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app),
                headers={"Authorization": f"Bearer {token}"},
            ) as http,
            Client(
                streamable_http_client(RESOURCE, http_client=http), mode=mode
            ) as mcp,
        ):
            assert (await mcp.list_tools()).tools[0].name == "get_project_overview"
            result = await mcp.call_tool("get_project_overview", {})
            assert not result.is_error and result.structured_content
            return result.structured_content["principal"]

    async def run() -> list[str]:
        async with app.router.lifespan_context(app):
            return await asyncio.gather(
                query("actor-a", "auto"), query("actor-b", "legacy")
            )

    assert asyncio.run(run()) == ["actor-a", "actor-b"]
