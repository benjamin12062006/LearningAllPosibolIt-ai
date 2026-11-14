"""Ejecuta el agente real con un catálogo sintético y respuestas guionizadas."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pytest
from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from qdrant_client import AsyncQdrantClient

from ktsu_ai.application.agent_application.agent_service import AgentService
from ktsu_ai.application.agent_ports.out_operation_gateway import OperationFailedError
from ktsu_ai.application.knowledge_application.dto_input_replace_source_input import (
    ReplaceSourceInput,
)
from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_application.dto_output_search_knowledge_output import (
    SearchKnowledgeOutput,
)
from ktsu_ai.application.knowledge_application.knowledge_service import KnowledgeService
from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.agent.agent_outcome import (
    PendingConfirmation,
    RunStatus,
    ToolCallRecord,
)
from ktsu_ai.domain.agent.agent_run import AgentRun, JsonObject, JsonValue, RunIdentity
from ktsu_ai.domain.knowledge.knowledge_document import (
    KnowledgeDocument,
    SourceKey,
    SourceType,
)
from ktsu_ai.http.agent_http.agent_dto import AgentOperationRequest
from ktsu_ai.infrastructure.agent_infrastructure.llamaindex_agent import LlamaIndexAgent
from ktsu_ai.infrastructure.knowledge_infrastructure.llamaindex_knowledge_index import (
    LlamaIndexKnowledgeIndex,
)
from tests.support.scripted_llm import ScriptedResponses, tool_call
from tests.support.word_hash_embedding import WordHashEmbedding

DATASET_PATH = Path(__file__).with_name("agent_cases.json")
SCOPE = AccessScope("org-demo", frozenset({"project-demo"}))
TEST_DEADLINE_SECONDS = 0.15
type Mode = Literal["execute", "prepare"]

# El Qdrant en memoria no crea índices de payload (sí aplica el filtro de alcance).
pytestmark = pytest.mark.filterwarnings(
    "ignore:Payload indexes have no effect in the local Qdrant"
)


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolTurn(Fixture):
    tool: str
    arguments: JsonObject
    repeat: int = Field(default=1, ge=1)


class TextTurn(Fixture):
    text: str


class SlowTurn(Fixture):
    wait_for_timeout: Literal[True]


@dataclass(frozen=True)
class OperationCall:
    mode: Mode
    operation: str
    arguments: JsonObject


class GatewayReply(Fixture):
    mode: Mode
    operation: str
    arguments: JsonObject
    result: JsonValue = None
    summary: str | None = None
    error: str | None = None

    @property
    def call(self) -> OperationCall:
        return OperationCall(self.mode, self.operation, self.arguments)


@dataclass(frozen=True)
class IndexedDocument:
    organization_id: str
    project_id: str
    document_id: str
    text: str


class Expected(Fixture):
    status: RunStatus
    calls: list[ToolCallRecord]
    gateway_calls: list[int] = Field(default_factory=list)
    knowledge_queries: list[str] = Field(default_factory=list)
    confirmation_from: int | None = None
    answer_contains: list[str] = Field(default_factory=list)
    tool_output_contains: list[str] = Field(default_factory=list)
    tool_output_excludes: list[str] = Field(default_factory=list)


class EvaluationCase(Fixture):
    id: str
    message: str
    offers: list[str]
    gateway: list[GatewayReply] = Field(default_factory=list)
    knowledge: list[IndexedDocument] = Field(default_factory=list)
    script: list[ToolTurn | TextTurn | SlowTurn]
    expected: Expected

    def confirmation(self) -> PendingConfirmation | None:
        if self.expected.confirmation_from is None:
            return None
        reply = self.gateway[self.expected.confirmation_from]
        assert reply.summary
        return PendingConfirmation(reply.operation, reply.arguments, reply.summary)


class Dataset(Fixture):
    operations: list[AgentOperationRequest]
    cases: list[EvaluationCase]


DATASET = TypeAdapter(Dataset).validate_json(DATASET_PATH.read_bytes())
OPERATIONS = {item.name: item.to_domain() for item in DATASET.operations}


@pytest.mark.parametrize("case", DATASET.cases, ids=lambda case: case.id)
def test_agent_evaluation(
    case: EvaluationCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_evaluate(case, monkeypatch))


async def _evaluate(case: EvaluationCase, monkeypatch: pytest.MonkeyPatch) -> None:
    identity = RunIdentity(case.id, SCOPE, "credential-evaluation-only")
    run = AgentRun(
        identity, case.message, (), tuple(OPERATIONS[name] for name in case.offers)
    )
    scripted, delay = _script(case)
    gateway = EvaluationGateway(identity, case.gateway)
    embedder = WordHashEmbedding()

    async with _memory_client() as client:
        index = LlamaIndexKnowledgeIndex(
            client, "evaluacion_conocimiento", embedder.dimensions, embedder
        )
        knowledge = RecordedKnowledge(index)
        await _seed_knowledge(knowledge, case.knowledge)
        service = AgentService(LlamaIndexAgent(scripted.llm), gateway, knowledge)
        if delay is not None:
            monkeypatch.setattr(
                "ktsu_ai.application.agent_application.agent_service.RUN_TIMEOUT_SECONDS",
                TEST_DEADLINE_SECONDS,
            )
            monkeypatch.setattr(type(scripted.llm), "achat", delay.achat)
        outcome = await service.run(run)

    expected = case.expected
    assert outcome.status == expected.status
    assert list(outcome.calls) == expected.calls
    assert outcome.confirmation == case.confirmation()
    assert gateway.calls == [
        case.gateway[index].call for index in expected.gateway_calls
    ]
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


class EvaluationGateway:
    def __init__(self, identity: RunIdentity, replies: list[GatewayReply]) -> None:
        self._identity = identity
        self._replies = replies
        self.calls: list[OperationCall] = []

    async def execute(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> JsonValue:
        return self._reply(
            identity, OperationCall("execute", operation, arguments)
        ).result

    async def prepare(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> str:
        reply = self._reply(identity, OperationCall("prepare", operation, arguments))
        assert reply.summary
        return reply.summary

    def _reply(self, identity: RunIdentity, call: OperationCall) -> GatewayReply:
        assert identity == self._identity
        self.calls.append(call)
        reply = next((reply for reply in self._replies if reply.call == call), None)
        assert reply is not None, f"Llamada fuera del caso de evaluación: {call}"
        if reply.error:
            raise OperationFailedError(reply.error)
        return reply


class RecordedKnowledge(KnowledgeService):
    def __init__(self, index: LlamaIndexKnowledgeIndex) -> None:
        super().__init__(index)
        self.queries: list[SearchKnowledgeInput] = []

    async def search(self, input: SearchKnowledgeInput) -> SearchKnowledgeOutput:
        self.queries.append(input)
        return await super().search(input)


async def _seed_knowledge(
    knowledge: KnowledgeService, documents: list[IndexedDocument]
) -> None:
    for document in documents:
        key = SourceKey(
            document.organization_id,
            document.project_id,
            SourceType.EVALUATION,
            document.document_id,
        )
        await knowledge.replace_source(
            ReplaceSourceInput(
                key, (KnowledgeDocument(document.document_id, document.text, {}),)
            )
        )


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


@asynccontextmanager
async def _memory_client() -> AsyncIterator[AsyncQdrantClient]:
    client = AsyncQdrantClient(location=":memory:")
    try:
        yield client
    finally:
        await client.close()
