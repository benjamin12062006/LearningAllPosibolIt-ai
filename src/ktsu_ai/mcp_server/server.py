"""Servidor MCP de KTSU (E6.7): un adaptador fino sobre el catálogo de Nest.

Las herramientas no se declaran aquí: se piden a Nest en cada `tools/list` y en
cada `tools/call`, así un permiso retirado o una credencial revocada dejan de
valer en la siguiente llamada. Una lectura devuelve su resultado; una escritura
solo deja una propuesta que la persona confirma en la aplicación.
"""

import json
from collections.abc import Callable
from typing import Any, Final

from mcp import types
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.shared.exceptions import MCPError

from ktsu_ai.application.integration_ports.out_integration_gateway import (
    IIntegrationGateway,
    IntegrationOperation,
    IntegrationRejectedError,
)
from ktsu_ai.domain.agent.agent_run import JsonValue

SERVER_NAME: Final = "ktsu"
INSTRUCTIONS: Final = (
    "Herramientas de un proyecto de KTSU. Las lecturas devuelven datos del "
    "proyecto. Las que cambian algo preparan una propuesta: si KTSU tiene la "
    "confirmación automática activada, se aplica en la misma llamada y la "
    "respuesta trae el resultado; si no, una persona la confirma en la "
    "aplicación."
)
WRITE_NOTE: Final = (
    " Cambia el proyecto: se aplica al momento si KTSU confirma "
    "automáticamente; si no, queda una propuesta para que la persona la "
    "confirme en la aplicación."
)
UNKNOWN_TOOL: Final = "Esa herramienta no está disponible para esta credencial."


def build_mcp_server(
    gateway: IIntegrationGateway | Callable[[], IIntegrationGateway],
) -> Server[Any]:
    def active_gateway() -> IIntegrationGateway:
        return gateway() if callable(gateway) else gateway

    async def list_tools(
        _: ServerRequestContext[Any], __: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        try:
            operations = await active_gateway().operations()
        except IntegrationRejectedError as error:
            raise MCPError(types.INVALID_REQUEST, str(error)) from None
        return types.ListToolsResult(tools=[_tool_of(item) for item in operations])

    async def call_tool(
        _: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        try:
            operations = await active_gateway().operations()
            operation = next(
                (item for item in operations if item.name == params.name), None
            )
            if operation is None:
                return _failure(UNKNOWN_TOOL)
            result = await active_gateway().call(operation, params.arguments or {})
        except IntegrationRejectedError as error:
            return _failure(str(error))
        if operation.level == "write":
            return _prepared(result)
        return _success(json.dumps(result, ensure_ascii=False), result)

    return Server(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


def _tool_of(operation: IntegrationOperation) -> types.Tool:
    is_read = operation.level == "read"
    return types.Tool(
        name=operation.name,
        description=operation.description + ("" if is_read else WRITE_NOTE),
        input_schema=dict(operation.input_schema),
        annotations=types.ToolAnnotations(
            read_only_hint=is_read,
            destructive_hint=False,
            open_world_hint=False,
        ),
    )


def _prepared(result: JsonValue) -> types.CallToolResult:
    """Lo que ve el cliente tras una escritura: aplicada, o dónde confirmarla."""
    if not isinstance(result, dict):
        return _success("Propuesta preparada.", result)
    summary = result.get("summary")
    if result.get("status") == "confirmed":
        outcome = json.dumps(result.get("result"), ensure_ascii=False)
        return _success(f"Aplicado: {summary}\nResultado: {outcome}", result)
    text = (
        f"Propuesta preparada: {summary}"
        if isinstance(summary, str)
        else "Propuesta preparada."
    )
    review = result.get("reviewPath")
    if isinstance(review, str):
        text += f"\nUna persona debe revisarla y confirmarla en KTSU: {review}"
    return _success(text, result)


def _success(text: str, result: JsonValue) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        # `structuredContent` tiene que ser un objeto.
        structured_content=result if isinstance(result, dict) else {"result": result},
    )


def _failure(message: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=message)], is_error=True
    )
