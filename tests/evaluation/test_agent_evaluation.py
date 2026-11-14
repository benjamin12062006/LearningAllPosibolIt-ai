"""Ejecuta el agente real con un catálogo sintético y respuestas guionizadas."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest
from llama_index.core.base.llms.types import ChatMessage, ChatResponse

from ktsu_ai.application.agent_application.agent_service import AgentService
from ktsu_ai.infrastructure.agent_infrastructure.llamaindex_agent import LlamaIndexAgent
from tests.evaluation.dataset import (
    DATASET,
    SCOPE,
    EvaluationCase,
    EvaluationGateway,
    SlowTurn,
    ToolTurn,
    knowledge_for,
)
from tests.support.scripted_llm import ScriptedResponses, tool_call

TEST_DEADLINE_SECONDS = 0.15

# El Qdrant en memoria no crea índices de payload (sí aplica el filtro de alcance).
pytestmark = pytest.mark.filterwarnings(
    "ignore:Payload indexes have no effect in the local Qdrant"
)


@pytest.mark.parametrize("case", DATASET.cases, ids=lambda case: case.id)
def test_agent_evaluation(
    case: EvaluationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_evaluate(case, monkeypatch))


async def _evaluate(case: EvaluationCase, monkeypatch: pytest.MonkeyPatch) -> None:
    scripted, delay = _script(case)
    gateway = EvaluationGateway(case.identity(), case.gateway)

    async with knowledge_for(case) as knowledge:
        service = AgentService(LlamaIndexAgent(scripted.llm), gateway, knowledge)
        if delay is not None:
            monkeypatch.setattr(
                "ktsu_ai.application.agent_application.agent_service.RUN_TIMEOUT_SECONDS",
                TEST_DEADLINE_SECONDS,
            )
            monkeypatch.setattr(type(scripted.llm), "achat", delay.achat)
        outcome = await service.run(case.run())

    expected = case.expected
    assert outcome.status == expected.status
    assert list(outcome.calls) == expected.calls
    assert outcome.confirmation == case.confirmation()
    assert gateway.calls == [
        case.gateway[index].call for index in expected.gateway_calls
    ]
    assert gateway.unexpected == []
    assert gateway.foreign_identities == []
    assert [(query.query, query.scope) for query in knowledge.queries] == [
        (query, SCOPE) for query in expected.knowledge_queries
    ]
    if delay is not None:
        assert delay.started and delay.cancelled
    assert all(text in outcome.answer for text in expected.answer_contains)
    tool_outputs = [
        message.content or ""
        for batch in scripted.messages
        for message in batch
        if message.role == "tool"
    ]
    assert all(
        any(text in output for output in tool_outputs)
        for text in expected.tool_output_contains
    )
    for text in expected.tool_output_excludes:
        assert text not in outcome.answer
        assert all(text not in output for output in tool_outputs)


def _script(case: EvaluationCase) -> tuple[ScriptedResponses, SlowModel | None]:
    replies: list[ChatMessage] = []
    for turn in case.script:
        if isinstance(turn, SlowTurn):
            assert len(case.script) == 1, (
                "La espera es el único turno del caso de plazo."
            )
            return ScriptedResponses(), SlowModel()
        if isinstance(turn, ToolTurn):
            for _ in range(turn.repeat):
                replies.append(tool_call(turn.tool, **turn.arguments))
        else:
            replies.append(ChatMessage(role="assistant", content=turn.text))
    return ScriptedResponses(*replies), None


class SlowModel:
    def __init__(self) -> None:
        self.started = False
        self.cancelled = False

    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: object
    ) -> ChatResponse:
        self.started = True
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("El modelo lento debe cancelarse.")
