"""Apoyo de la prueba local de Nest y del cliente MCP. Usa datos sintéticos."""

import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import uvicorn
from llama_index.core.base.llms.types import ChatMessage
from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError
from qdrant_client import AsyncQdrantClient

from ktsu_ai.bootstrap.app import create_app
from ktsu_ai.config.loader import load_configuration
from tests.support.scripted_llm import ScriptedResponses, tool_call
from tests.support.word_hash_embedding import WordHashEmbedding


async def serve() -> None:
    config = load_configuration(env_file=None)
    config.embedding.dimensions = 64
    suffix = uuid4().hex
    config.knowledge.collection = f"test_mcp_knowledge_{suffix}"
    config.agent_tools_collection = f"test_mcp_tools_{suffix}"
    scripted = ScriptedResponses(
        tool_call("get_sheet_schema"),
        tool_call(
            "propose_sheet_layout",
            name="Hoja del chat",
            columns=[{"name": "SKU", "type": "text"}],
        ),
        ChatMessage(role="assistant", content="Terminó la comprobación."),
    )

    qdrant = os.environ.get("KTSU_TEST_QDRANT_URL")
    if qdrant and urlsplit(qdrant).hostname != "127.0.0.1":
        raise ValueError("La prueba requiere un Qdrant local desechable.")
    index = (
        AsyncQdrantClient(url=qdrant)
        if qdrant
        else AsyncQdrantClient(location=":memory:")
    )
    with patch("ktsu_ai.bootstrap.app.create_client", return_value=index):
        app = create_app(config, WordHashEmbedding(), agent_llm=scripted.llm)

    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            print(listener.getsockname()[1], flush=True)
            await server.serve(sockets=[listener])
    finally:
        if qdrant:
            cleanup = AsyncQdrantClient(url=qdrant)
            try:
                await cleanup.delete_collection(config.knowledge.collection)
                await cleanup.delete_collection(config.agent_tools_collection)
            finally:
                await cleanup.close()


def local_mcp() -> StdioServerParameters:
    return StdioServerParameters(
        command=str(Path(sys.executable).with_name("ktsu-mcp")),
        env={
            "KTSU_NEST_URL": os.environ["NEST_AGENT_BASE_URL"],
            "KTSU_MCP_ADAPTER_TOKEN": os.environ["KTSU_MCP_ADAPTER_TOKEN"],
            "KTSU_MCP_CREDENTIAL": os.environ["KTSU_MCP_CREDENTIAL"],
        },
    )


async def verify() -> None:
    workbook_id = os.environ["KTSU_TEST_WORKBOOK"]
    worksheet_id = os.environ["KTSU_TEST_WORKSHEET"]
    project_id = os.environ["KTSU_TEST_PROJECT"]
    foreign_worksheet_ids = json.loads(os.environ["KTSU_TEST_FOREIGN_WORKSHEETS"])

    async with Client(local_mcp(), mode="legacy", read_timeout_seconds=10) as client:
        overview = await client.call_tool("get_project_overview")
        assert not overview.is_error
        assert overview.structured_content
        assert overview.structured_content["project"]["id"] == project_id

    async with Client(local_mcp(), read_timeout_seconds=25) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert {"search_knowledge", "get_sheet_schema", "propose_sheet_layout"} <= tools
        assert "publish_feed" not in tools
        blocked = await client.call_tool("publish_feed", {})
        assert blocked.is_error
        schema = await client.call_tool(
            "get_sheet_schema", {"worksheetId": worksheet_id}
        )
        assert not schema.is_error
        assert schema.structured_content
        assert schema.structured_content["id"] == worksheet_id
        for foreign_worksheet_id in foreign_worksheet_ids:
            foreign = await client.call_tool(
                "get_sheet_schema", {"worksheetId": foreign_worksheet_id}
            )
            assert foreign.is_error
        search = await client.call_tool("search_knowledge", {"query": "propioverde"})
        assert not search.is_error
        assert search.structured_content
        hits = search.structured_content["hits"]
        assert any("propioverde" in hit["text"] for hit in hits)
        assert {hit["projectId"] for hit in hits} == {project_id}
        assert not any("ajenomarcador" in hit["text"] for hit in hits)
        result = await client.call_tool(
            "propose_sheet_layout",
            {
                "workbookId": workbook_id,
                "name": "Hoja desde MCP",
                "columns": [{"name": "SKU", "type": "text"}],
            },
        )
        assert not result.is_error
        assert result.structured_content
        print(json.dumps({"proposalId": result.structured_content["proposalId"]}))


async def verify_revocation() -> None:
    async with Client(local_mcp(), read_timeout_seconds=10) as client:
        try:
            await client.list_tools()
        except MCPError as error:
            assert "revocada" in str(error)
        else:
            raise AssertionError("Una credencial revocada listó herramientas.")


if __name__ == "__main__":
    scenarios = {"serve": serve, "verify": verify, "revoked": verify_revocation}
    asyncio.run(scenarios[sys.argv[1]]())
