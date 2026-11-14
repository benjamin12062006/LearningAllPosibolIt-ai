"""Reglas de herramientas de un solo turno, independientes de LlamaIndex."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Final

from ktsu_ai.application.agent_ports.out_operation_gateway import (
    IOperationGateway,
    OperationFailedError,
)
from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_ports.in_knowledge_use_case import IKnowledgeUseCase
from ktsu_ai.common.error import AppError
from ktsu_ai.domain.agent.agent_outcome import (
    AgentOutcome,
    CallStatus,
    PendingConfirmation,
    ToolCallRecord,
)
from ktsu_ai.domain.agent.agent_run import (
    ASK_FOR_CLARIFICATION,
    SEARCH_KNOWLEDGE,
    AgentOperation,
    AgentRun,
    JsonObject,
    OperationLevel,
)

MAX_TOOL_CALLS: Final = 8
MAX_TOOL_OUTPUT_LENGTH: Final = 16_000
MAX_TOOL_OUTPUT_TOTAL: Final = 64 * 1024
KNOWLEDGE_RESULTS: Final = 8
MAX_QUERY_LENGTH: Final = 1_000
TOOL_LIMIT_MESSAGE: Final = "Se alcanzó el límite de llamadas a herramientas."
TIME_LIMIT_MESSAGE: Final = "Se agotó el tiempo de ejecución del agente."
MODEL_LIMIT_MESSAGE: Final = "Se alcanzó el límite de turnos del agente."


@dataclass(frozen=True)
class ToolResult:
    status: CallStatus
    content: str


class AgentToolbox:
    def __init__(
        self,
        run: AgentRun,
        operations: tuple[AgentOperation, ...],
        gateway: IOperationGateway,
        knowledge: IKnowledgeUseCase,
        validates: Callable[[JsonObject, JsonObject], bool],
    ) -> None:
        self._identity = run.identity
        self._operations = {operation.name: operation for operation in operations}
        self._gateway = gateway
        self._knowledge = knowledge
        self._validates = validates
        self._lock = asyncio.Lock()
        self._calls: list[ToolCallRecord] = []
        self._pending: PendingConfirmation | None = None
        self._question: str | None = None
        self._tool_limit_reached = False
        self._output_bytes_left = MAX_TOOL_OUTPUT_TOTAL

    async def invoke(self, name: str, arguments: JsonObject) -> ToolResult:
        # Un lote del modelo puede contener varias escrituras que compitan por confirmar.
        async with self._lock:
            result = await self._invoke(name, arguments)
            self._calls.append(ToolCallRecord(name, result.status))
            return result

    def outcome(self, answer: str, limit: str | None = None) -> AgentOutcome:
        calls = tuple(self._calls)
        if self._pending is not None:
            return AgentOutcome(
                "confirmation_required", self._pending.summary, calls, self._pending
            )
        if self._question is not None:
            return AgentOutcome("needs_clarification", self._question, calls)
        if self._tool_limit_reached or limit:
            return AgentOutcome("limit_reached", limit or TOOL_LIMIT_MESSAGE, calls)
        return AgentOutcome("answered", answer, calls)

    async def _invoke(self, name: str, arguments: JsonObject) -> ToolResult:
        if len(self._calls) >= MAX_TOOL_CALLS:
            self._tool_limit_reached = True
            return ToolResult("rejected", TOOL_LIMIT_MESSAGE)
        if self._pending is not None or self._question is not None:
            return ToolResult("rejected", "La ejecución ya espera una respuesta.")
        if name == SEARCH_KNOWLEDGE:
            return await self._search(arguments)
        if name == ASK_FOR_CLARIFICATION:
            return self._clarify(arguments)
        operation = self._operations.get(name)
        if operation is None:
            return ToolResult(
                "rejected", "La herramienta solicitada no está disponible."
            )
        if not self._validates(operation.input_schema, arguments):
            return ToolResult("rejected", "Los argumentos no cumplen el esquema.")
        return await self._call_nest(operation, arguments)

    async def _call_nest(
        self, operation: AgentOperation, arguments: JsonObject
    ) -> ToolResult:
        try:
            if operation.level is OperationLevel.READ:
                value = await self._gateway.execute(
                    self._identity, operation.name, arguments
                )
                return ToolResult("succeeded", self._encode(value))

            summary = await self._gateway.prepare(
                self._identity, operation.name, arguments
            )
            self._pending = PendingConfirmation(operation.name, arguments, summary)
            return ToolResult("prepared", summary)
        except OperationFailedError as error:
            return ToolResult("failed", self._bound_output(str(error)))

    async def _search(self, arguments: JsonObject) -> ToolResult:
        query = _single_text_argument(arguments, "query")
        if query is None:
            return ToolResult("rejected", "Indica una consulta válida.")
        search = SearchKnowledgeInput(
            scope=self._identity.scope,
            query=query,
            limit=KNOWLEDGE_RESULTS,
            source_types=frozenset(),
        )
        try:
            output = await self._knowledge.search(search)
        except AppError as error:
            return ToolResult("failed", self._bound_output(error.definition.message.es))
        return ToolResult(
            "succeeded", self._encode([asdict(hit) for hit in output.hits])
        )

    def _clarify(self, arguments: JsonObject) -> ToolResult:
        question = _single_text_argument(arguments, "question")
        if question is None:
            return ToolResult("rejected", "Indica una pregunta de aclaración válida.")
        self._question = question
        return ToolResult("succeeded", question)

    def _encode(self, value: object) -> str:
        return self._bound_output(json.dumps(value, ensure_ascii=False))

    def _bound_output(self, content: str) -> str:
        limited = content[:MAX_TOOL_OUTPUT_LENGTH].encode()
        limited = limited[: self._output_bytes_left]
        self._output_bytes_left -= len(limited)
        return limited.decode(errors="ignore")


def _single_text_argument(arguments: JsonObject, name: str) -> str | None:
    value = arguments.get(name)
    if set(arguments) != {name} or not isinstance(value, str):
        return None
    value = value.strip()
    if 0 < len(value) <= MAX_QUERY_LENGTH:
        return value
    return None
