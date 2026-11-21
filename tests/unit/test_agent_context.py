"""Lo que el agente sabe antes de empezar: la ficha del proyecto y Qdrant (plan 10 de Nest, E3)."""

import asyncio
from dataclasses import replace

import pytest
from llama_index.core.base.llms.types import ChatMessage

from ktsu_ai.application.agent_application import agent_service
from ktsu_ai.application.agent_application.agent_service import AgentService
from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_application.dto_output_search_knowledge_output import (
    SearchKnowledgeOutput,
)
from ktsu_ai.application.knowledge_ports.in_knowledge_use_case import IKnowledgeUseCase
from ktsu_ai.domain.agent.agent_run import HistoryMessage, JsonObject
from ktsu_ai.infrastructure.agent_infrastructure.llamaindex_agent import LlamaIndexAgent
from tests.http.test_knowledge_routes import FakeKnowledge
from tests.support.scripted_llm import ScriptedResponses
from tests.unit.test_agent import RUN, Gateway

PROJECT: JsonObject = {
    "project": {"name": "Tienda Sur", "currency": "BOB"},
    "sheets": [
        {"id": "h-1", "name": "Productos", "rowCount": 120},
        {"id": "h-2", "name": "Stock", "rowCount": 80},
    ],
}


def system_prompt_of(scripted: ScriptedResponses) -> str:
    return scripted.messages[0][0].content or ""


def run_with(
    prefetch: IKnowledgeUseCase | None, project: JsonObject | None = PROJECT
) -> ScriptedResponses:
    scripted = ScriptedResponses(ChatMessage(role="assistant", content="Listo."))
    service = AgentService(
        LlamaIndexAgent(scripted.llm),
        Gateway(),
        FakeKnowledge(),
        prefetch=prefetch,
    )
    run = replace(
        RUN,
        message="sí, hazlo",
        history=(
            HistoryMessage("user", "¿Qué productos no tienen imagen?"),
            HistoryMessage("assistant", "Tres productos."),
            HistoryMessage("user", "Quítalos del feed"),
            HistoryMessage("assistant", "¿Seguro?"),
        ),
        project=project,
    )
    asyncio.run(service.run(run))
    return scripted


def test_the_project_sheet_reaches_the_model_in_toon() -> None:
    scripted = run_with(prefetch=None)

    prompt = system_prompt_of(scripted)
    assert "Ficha del proyecto que preparó KTSU" in prompt
    assert "name: Tienda Sur" in prompt
    assert "sheets[2]{id,name,rowCount}:" in prompt
    assert "Conocimiento del proyecto" not in prompt


def test_qdrant_is_searched_first_with_the_earlier_questions_and_the_run_scope() -> (
    None
):
    knowledge = FakeKnowledge()

    scripted = run_with(prefetch=knowledge)

    [search] = knowledge.searches
    assert search.scope == RUN.identity.scope
    assert search.query == (
        "¿Qué productos no tienen imagen?\nQuítalos del feed\nsí, hazlo"
    )
    prompt = system_prompt_of(scripted)
    assert "Conocimiento del proyecto relacionado" in prompt
    assert "Zapatillas rojas" in prompt


def test_a_long_query_keeps_the_current_message() -> None:
    run = replace(
        RUN, message="mensaje actual", history=(HistoryMessage("user", "x" * 5_000),)
    )

    assert agent_service.prefetch_query(run).endswith("mensaje actual")
    assert len(agent_service.prefetch_query(run)) == 1_000


def test_the_run_goes_on_when_qdrant_is_down() -> None:
    knowledge = FakeKnowledge()
    knowledge.unavailable = True

    scripted = run_with(prefetch=knowledge)

    assert "Conocimiento del proyecto" not in system_prompt_of(scripted)
    assert scripted.messages[-1]


def test_the_run_goes_on_when_qdrant_is_slow(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowKnowledge(FakeKnowledge):
        async def search(self, input: SearchKnowledgeInput) -> SearchKnowledgeOutput:
            await asyncio.sleep(5)
            return await super().search(input)

    monkeypatch.setattr(agent_service, "PREFETCH_TIMEOUT_SECONDS", 0.05)

    scripted = run_with(prefetch=SlowKnowledge())

    assert "Conocimiento del proyecto" not in system_prompt_of(scripted)
    assert "Ficha del proyecto" in system_prompt_of(scripted)
