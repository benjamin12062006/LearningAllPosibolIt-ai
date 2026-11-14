"""Selección semántica sobre Qdrant y su intersección con el catálogo del run."""

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import pytest
from llama_index.core.base.llms.types import ChatMessage
from qdrant_client import AsyncQdrantClient

from ktsu_ai.application.agent_application.agent_service import AgentService
from ktsu_ai.domain.agent.agent_run import AgentOperation, OperationLevel
from ktsu_ai.infrastructure.agent_infrastructure.llamaindex_agent import LlamaIndexAgent
from ktsu_ai.infrastructure.agent_infrastructure.qdrant_operation_selector import (
    MAX_SELECTED_OPERATIONS,
    QdrantOperationSelector,
)
from tests.http.test_knowledge_routes import FakeKnowledge
from tests.support.scripted_llm import ScriptedResponses, tool_call
from tests.support.word_hash_embedding import WordHashEmbedding
from tests.unit.test_agent import READ, RUN, Gateway


@pytest.mark.parametrize(
    "backend", ["memory", pytest.param("server", marks=pytest.mark.qdrant)]
)
def test_selects_relevant_authorized_tools_from_separate_collection(
    backend: str,
) -> None:
    async def scenario() -> None:
        if backend == "memory":
            client = AsyncQdrantClient(location=":memory:")
        else:
            client = AsyncQdrantClient(url=os.environ["TEST_QDRANT_URL"])

        embedder = WordHashEmbedding()
        collection = f"prueba_agente_{uuid4().hex}"
        selector = QdrantOperationSelector(client, embedder, collection, 64)
        current = replace(READ, description="inventario inventario existencias")
        stale = replace(current, description="rotación de precios")
        other = replace(current, name="private_inventory")
        less_relevant = tuple(
            AgentOperation(
                f"tool_{index}",
                "tratamiento de texto",
                READ.input_schema,
                OperationLevel.READ,
            )
            for index in range(MAX_SELECTED_OPERATIONS)
        )
        run = replace(
            RUN, message="inventario existencias", operations=(current, *less_relevant)
        )
        script = ScriptedResponses(
            tool_call(other.name, limit=1),
            ChatMessage(role="assistant", content="Listo."),
        )
        gateway = Gateway()
        service = AgentService(
            LlamaIndexAgent(script.llm), gateway, FakeKnowledge(), selector
        )
        try:
            await selector.select(replace(run, operations=(other, stale)))
            names = await selector.select(run)
            outcome = await service.run(run)
            assert names[0] == current.name
            assert len(names) == MAX_SELECTED_OPERATIONS
            offered = {tool["function"]["name"] for tool in script.schemas}
            fixed_tools = {"search_knowledge", "ask_for_clarification"}
            assert fixed_tools <= offered
            assert len(offered - fixed_tools) == MAX_SELECTED_OPERATIONS
            assert current.name in offered
            assert offered - fixed_tools <= {
                operation.name for operation in run.operations
            }
            assert gateway.calls == []
            assert outcome.calls[0].status == "rejected"
            assert embedder.embedded_texts == len(run.operations) + 2
        finally:
            await client.delete_collection(collection)
            await client.close()

    asyncio.run(scenario())
