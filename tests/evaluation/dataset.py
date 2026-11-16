"""Casos de evaluación del agente y dobles comunes al guion y a Gemini real."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from qdrant_client import AsyncQdrantClient

from ktsu_ai.application.agent_ports.out_operation_gateway import (
    OperationFailedError,
    Preparation,
)
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
from ktsu_ai.domain.agent.agent_run import (
    AgentOperation,
    AgentRun,
    JsonObject,
    JsonValue,
    RunIdentity,
)
from ktsu_ai.domain.knowledge.knowledge_document import (
    KnowledgeDocument,
    SourceKey,
    SourceType,
)
from ktsu_ai.http.agent_http.agent_dto import AgentOperationRequest
from ktsu_ai.infrastructure.knowledge_infrastructure.llamaindex_knowledge_index import (
    LlamaIndexKnowledgeIndex,
)
from tests.support.word_hash_embedding import WordHashEmbedding

DATASET_PATH = Path(__file__).with_name("agent_cases.json")
SCOPE = AccessScope("org-demo", frozenset({"project-demo"}))
UNEXPECTED_CALL_MESSAGE = "En la evaluación no hay datos para esa llamada."
type Mode = Literal["execute", "prepare"]


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
    # El caso fuerza al modelo (plazo, presupuesto): solo tiene sentido con guion.
    scripted_only: bool = False

    def identity(self) -> RunIdentity:
        return RunIdentity(self.id, SCOPE, "credential-evaluation-only")

    def run(self) -> AgentRun:
        operations = tuple(OPERATIONS[name] for name in self.offers)
        return AgentRun(self.identity(), self.message, (), operations)

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
OPERATIONS: dict[str, AgentOperation] = {
    item.name: item.to_domain() for item in DATASET.operations
}


class EvaluationGateway:
    """Nest simulado: responde lo que prevé el caso y anota todo lo demás.

    Una excepción dentro de una herramienta no hace fallar la prueba (LlamaIndex
    la convierte en un error para el modelo). Por eso lo no previsto se anota
    aquí y se comprueba al terminar la ejecución.
    """

    def __init__(self, identity: RunIdentity, replies: list[GatewayReply]) -> None:
        self._identity = identity
        self._replies = replies
        self.calls: list[OperationCall] = []
        self.unexpected: list[OperationCall] = []
        self.foreign_identities: list[RunIdentity] = []

    async def execute(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> JsonValue:
        call = OperationCall("execute", operation, arguments)
        return self._reply(identity, call).result

    async def prepare(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> Preparation:
        reply = self._reply(identity, OperationCall("prepare", operation, arguments))
        assert reply.summary
        return Preparation(reply.summary)

    def _reply(self, identity: RunIdentity, call: OperationCall) -> GatewayReply:
        self.calls.append(call)
        if identity != self._identity:
            self.foreign_identities.append(identity)
        reply = next((reply for reply in self._replies if reply.call == call), None)
        if reply is None:
            self.unexpected.append(call)
            raise OperationFailedError(UNEXPECTED_CALL_MESSAGE)
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


@asynccontextmanager
async def knowledge_for(case: EvaluationCase) -> AsyncIterator[RecordedKnowledge]:
    """Qdrant en memoria con los documentos del caso, también de otros inquilinos."""
    embedder = WordHashEmbedding()
    client = AsyncQdrantClient(location=":memory:")
    try:
        index = LlamaIndexKnowledgeIndex(
            client, "evaluacion_conocimiento", embedder.dimensions, embedder
        )
        knowledge = RecordedKnowledge(index)
        for document in case.knowledge:
            await _seed(knowledge, document)
        yield knowledge
    finally:
        await client.close()


async def _seed(knowledge: KnowledgeService, document: IndexedDocument) -> None:
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
