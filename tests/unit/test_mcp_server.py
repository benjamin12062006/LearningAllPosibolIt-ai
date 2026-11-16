"""El servidor MCP ofrece lo que Nest autoriza y nada más (E6.7)."""

import asyncio
import json
from uuid import UUID

import httpx
import pytest
from mcp import Client, types
from mcp.shared.exceptions import MCPError

from ktsu_ai.application.integration_ports.out_integration_gateway import (
    IntegrationOperation,
    IntegrationRejectedError,
)
from ktsu_ai.domain.agent.agent_run import JsonObject, JsonValue
from ktsu_ai.infrastructure.integration_infrastructure.nest_integration_gateway import (
    UNAVAILABLE,
    NestIntegrationGateway,
)
from ktsu_ai.mcp_server.server import UNKNOWN_TOOL, WRITE_NOTE, build_mcp_server

SCHEMA: JsonObject = {
    "type": "object",
    "properties": {"worksheetId": {"type": "string"}},
    "additionalProperties": False,
}
READ = IntegrationOperation("get_sheet_schema", "Columnas de una hoja.", SCHEMA, "read")
WRITE = IntegrationOperation("suggest_view", "Propone una vista.", SCHEMA, "write")
ADAPTER_TOKEN = "token-del-adaptador-0123456789abcdef"
CREDENTIAL = "ktsu1_credencial-de-pruebas"


class FakeGateway:
    """Hace de Nest: un catálogo y un resultado o un rechazo por operación."""

    def __init__(self, *operations: IntegrationOperation) -> None:
        self.catalog = list(operations)
        self.calls: list[tuple[str, JsonObject]] = []
        self.results: dict[str, JsonValue] = {}
        self.rejection: str | None = None

    async def operations(self) -> tuple[IntegrationOperation, ...]:
        if self.rejection:
            raise IntegrationRejectedError(self.rejection)
        return tuple(self.catalog)

    async def call(
        self, operation: IntegrationOperation, arguments: JsonObject
    ) -> JsonValue:
        self.calls.append((operation.name, arguments))
        return self.results.get(operation.name)


def text_of(result: object) -> str:
    assert isinstance(result, types.CallToolResult)
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return block.text


def test_las_herramientas_son_el_catalogo_de_nest() -> None:
    async def scenario() -> list[types.Tool]:
        async with Client(build_mcp_server(FakeGateway(READ, WRITE))) as client:
            return (await client.list_tools()).tools

    read, write = asyncio.run(scenario())

    assert (read.name, read.description, read.input_schema) == (
        READ.name,
        READ.description,
        SCHEMA,
    )
    assert read.annotations is not None and read.annotations.read_only_hint is True
    # Una escritura avisa de que solo prepara, y no se marca como lectura.
    assert write.description == WRITE.description + WRITE_NOTE
    assert write.annotations is not None and write.annotations.read_only_hint is False


def test_una_lectura_devuelve_el_resultado_de_nest() -> None:
    gateway = FakeGateway(READ)
    gateway.results[READ.name] = {"columns": [{"name": "Precio"}]}

    async def scenario() -> object:
        async with Client(build_mcp_server(gateway)) as client:
            return await client.call_tool(READ.name, {"worksheetId": "w1"})

    result = asyncio.run(scenario())

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is False
    assert json.loads(text_of(result)) == {"columns": [{"name": "Precio"}]}
    assert result.structured_content == {"columns": [{"name": "Precio"}]}
    assert gateway.calls == [(READ.name, {"worksheetId": "w1"})]


def test_una_escritura_solo_deja_la_propuesta_para_confirmar() -> None:
    gateway = FakeGateway(WRITE)
    gateway.results[WRITE.name] = {
        "proposalId": "p1",
        "summary": "Vista «Caros»",
        "reviewPath": "/organizations/o1/projects/p1/integrations/proposals/p1",
    }

    async def scenario() -> object:
        async with Client(build_mcp_server(gateway)) as client:
            return await client.call_tool(WRITE.name, {})

    text = text_of(asyncio.run(scenario()))

    assert "Propuesta preparada: Vista «Caros»" in text
    assert "/integrations/proposals/p1" in text


def test_una_escritura_confirmada_por_ktsu_dice_que_quedo_aplicada() -> None:
    gateway = FakeGateway(WRITE)
    gateway.results[WRITE.name] = {
        "proposalId": "p1",
        "status": "confirmed",
        "summary": "Vista «Caros»",
        "result": {"savedViewId": "v1"},
    }

    async def scenario() -> object:
        async with Client(build_mcp_server(gateway)) as client:
            return await client.call_tool(WRITE.name, {})

    text = text_of(asyncio.run(scenario()))

    assert "Aplicado: Vista «Caros»" in text
    assert '"savedViewId": "v1"' in text
    assert "debe revisarla" not in text


def test_una_herramienta_fuera_del_catalogo_no_llega_a_nest() -> None:
    gateway = FakeGateway(READ)

    async def scenario() -> object:
        async with Client(build_mcp_server(gateway)) as client:
            return await client.call_tool("publish_feed", {})

    result = asyncio.run(scenario())

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is True
    assert text_of(result) == UNKNOWN_TOOL
    assert gateway.calls == []


def test_si_nest_rechaza_el_cliente_ve_su_mensaje_publico() -> None:
    gateway = FakeGateway(READ)
    gateway.rejection = "La credencial de integración no es válida."

    async def scenario() -> object:
        async with Client(build_mcp_server(gateway)) as client:
            with pytest.raises(MCPError, match="La credencial de integración"):
                await client.list_tools()
            return await client.call_tool(READ.name, {})

    result = asyncio.run(scenario())

    assert isinstance(result, types.CallToolResult)
    assert result.is_error is True
    assert text_of(result) == "La credencial de integración no es válida."


def gateway_for(
    handler: httpx.MockTransport,
) -> tuple[NestIntegrationGateway, httpx.AsyncClient]:
    client = httpx.AsyncClient(base_url="http://nest.test", transport=handler)
    return NestIntegrationGateway(client, ADAPTER_TOKEN, CREDENTIAL), client


def test_la_pasarela_manda_las_dos_credenciales_y_el_modo_de_cada_operacion() -> None:
    seen: list[httpx.Request] = []

    def nest(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "operations": [
                        {
                            "name": READ.name,
                            "description": READ.description,
                            "inputSchema": SCHEMA,
                            "level": "read",
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"ok": True})

    async def scenario() -> tuple[
        tuple[IntegrationOperation, ...], JsonValue, JsonValue
    ]:
        gateway, client = gateway_for(httpx.MockTransport(nest))
        async with client:
            return (
                await gateway.operations(),
                await gateway.call(READ, {"worksheetId": "w1"}),
                await gateway.call(WRITE, {}),
            )

    operations, read, _ = asyncio.run(scenario())

    assert operations == (READ,)
    assert read == {"ok": True}
    assert [request.url.path for request in seen] == [
        "/internal/v1/mcp-integrations/operations",
        "/internal/v1/mcp-integrations/operations/get_sheet_schema",
        "/internal/v1/mcp-integrations/operations/suggest_view",
    ]
    for request in seen:
        assert request.headers["authorization"] == f"Bearer {ADAPTER_TOKEN}"
        assert request.headers["x-ktsu-delegation"] == f"Bearer {CREDENTIAL}"
    executed = json.loads(seen[1].content)
    assert UUID(executed.pop("callId")).version == 4
    assert executed == {
        "mode": "execute",
        "arguments": {"worksheetId": "w1"},
    }
    prepared = json.loads(seen[2].content)
    assert UUID(prepared["callId"]).version == 4
    assert prepared["mode"] == "prepare"


def test_la_pasarela_traduce_rechazos_y_fallos_sin_filtrar_detalles() -> None:
    def rejected(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"code": "X", "message": {"es": "Credencial revocada."}}
        )

    def broken(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="stack trace con secretos")

    def odd_catalog(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"operations": [{"name": "DROP TABLE"}]})

    async def message_of(handler: httpx.MockTransport) -> str:
        gateway, client = gateway_for(handler)
        async with client:
            try:
                await gateway.operations()
            except IntegrationRejectedError as error:
                return str(error)
        return "sin error"

    assert asyncio.run(message_of(httpx.MockTransport(rejected))) == (
        "Credencial revocada."
    )
    assert asyncio.run(message_of(httpx.MockTransport(broken))) == UNAVAILABLE
    assert asyncio.run(message_of(httpx.MockTransport(odd_catalog))) == UNAVAILABLE
