"""Reglas de herramientas de un solo turno, independientes de LlamaIndex."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from ktsu_ai.application.agent_application.model_text import to_model_text
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
    JsonValue,
    OperationLevel,
)
from ktsu_ai.domain.knowledge.knowledge_document import KnowledgeHit

# Tiene que coincidir con `AGENT_RUN_LIMITS.calls` de Nest (plan 10, D2).
MAX_TOOL_CALLS: Final = 40
# Igual que `readResultBytes` de Nest: una lectura más grande ya es un 422 allí.
MAX_RESULT_BYTES: Final = 60 * 1024
MAX_OUTPUT_BYTES_PER_RUN: Final = 512 * 1024
# Lo que se aparta para el aviso de recorte.
NOTICE_RESERVE_BYTES: Final = 256
# Por debajo de esto, recortar ya no deja nada útil que leer.
MIN_USEFUL_BYTES: Final = 1024
KNOWLEDGE_RESULTS: Final = 8
MAX_QUERY_LENGTH: Final = 1_000
TOOL_LIMIT_MESSAGE: Final = (
    "Se alcanzó el límite de llamadas de este turno. "
    "Puedes continuar la tarea con otro mensaje."
)
TIME_LIMIT_MESSAGE: Final = "Se agotó el tiempo de ejecución del agente."
MODEL_LIMIT_MESSAGE: Final = "Se alcanzó el límite de turnos del agente."
ENGLISH_LIMITS: Final = {
    TOOL_LIMIT_MESSAGE: "This turn reached its tool call limit. You can continue in another message.",
    TIME_LIMIT_MESSAGE: "The assistant ran out of time.",
    MODEL_LIMIT_MESSAGE: "The assistant reached its turn limit.",
}
TRUNCATED_NOTICE: Final = {
    "es": "[Resultado recortado: se muestran {shown} de {total} caracteres. "
    "Pide menos filas o columnas, o la página siguiente.]",
    "en": "[Result truncated: showing {shown} of {total} characters. "
    "Ask for fewer rows or columns, or for the next page.]",
}
BUDGET_EXHAUSTED: Final = {
    "es": "Se agotó el espacio para resultados de este turno. Responde con lo "
    "que ya tienes; la persona puede pedirte que continúes.",
    "en": "This turn has no room left for tool results. Answer with what you "
    "have; the person can ask you to continue.",
}


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
        knowledge: IKnowledgeUseCase | None,
        validates: Callable[[JsonObject, JsonObject], bool],
    ) -> None:
        self._identity = run.identity
        self._language = run.context.language
        self._operations = {operation.name: operation for operation in operations}
        self._gateway = gateway
        self._knowledge = knowledge
        self._validates = validates
        self._lock = asyncio.Lock()
        self._calls: list[ToolCallRecord] = []
        self._pending: PendingConfirmation | None = None
        self._question: str | None = None
        self._tool_limit_reached = False
        self._output_bytes_left = MAX_OUTPUT_BYTES_PER_RUN
        self._read_results: dict[tuple[str, str], ToolResult] = {}

    @property
    def awaits_confirmation(self) -> bool:
        """Si una escritura dejó una propuesta que la persona tiene que confirmar."""
        return self._pending is not None

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
            message = limit or TOOL_LIMIT_MESSAGE
            if self._language == "en":
                message = ENGLISH_LIMITS.get(message, message)
            return AgentOutcome("limit_reached", message, calls)
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
                key = (operation.name, json.dumps(arguments, sort_keys=True))
                cached = self._read_results.get(key)
                if cached is not None:
                    return cached
                value = await self._gateway.execute(
                    self._identity, operation.name, arguments
                )
                result = ToolResult("succeeded", self._for_model(value))
                self._read_results[key] = result
                return result

            preparation = await self._gateway.prepare(
                self._identity, operation.name, arguments
            )
            if preparation.applied:
                # Nest ya la aplicó: el modelo sigue con el resultado.
                applied = {"applied": preparation.summary, "result": preparation.result}
                return ToolResult("succeeded", self._for_model(applied))
            self._pending = PendingConfirmation(
                operation.name, arguments, preparation.summary
            )
            return ToolResult("prepared", preparation.summary)
        except OperationFailedError as error:
            return ToolResult("failed", self._fit(error.for_model(self._language)))

    async def _search(self, arguments: JsonObject) -> ToolResult:
        query = _single_text_argument(arguments, "query")
        if query is None:
            return ToolResult("rejected", "Indica una consulta válida.")
        if self._knowledge is None:
            try:
                value = await self._gateway.execute(
                    self._identity, SEARCH_KNOWLEDGE, {"query": query}
                )
            except OperationFailedError as error:
                return ToolResult("failed", self._fit(error.for_model(self._language)))
            return ToolResult("succeeded", self._for_model(value))
        search = SearchKnowledgeInput(
            scope=self._identity.scope,
            query=query,
            limit=KNOWLEDGE_RESULTS,
            source_types=frozenset(),
        )
        try:
            output = await self._knowledge.search(search)
        except AppError as error:
            message = error.definition.message
            return ToolResult(
                "failed",
                self._fit(self._in_language({"es": message.es, "en": message.en})),
            )
        return ToolResult("succeeded", self._for_model(knowledge_rows(output.hits)))

    def _clarify(self, arguments: JsonObject) -> ToolResult:
        question = _single_text_argument(arguments, "question")
        if question is None:
            return ToolResult("rejected", "Indica una pregunta de aclaración válida.")
        self._question = question
        return ToolResult("succeeded", question)

    def _for_model(self, value: JsonValue) -> str:
        return self._fit(to_model_text(value))

    def _fit(self, content: str) -> str:
        """Lo que cabe en un resultado y en lo que queda del turno.

        Recorta por líneas, para no dejar una fila a medias, y lo avisa. Nunca
        devuelve un texto vacío: el modelo tiene que saber qué pasó (ficha 12, E9).
        """
        allowance = min(MAX_RESULT_BYTES, self._output_bytes_left)
        encoded = content.encode()
        if len(encoded) <= allowance:
            self._output_bytes_left -= len(encoded)
            return content
        if allowance - NOTICE_RESERVE_BYTES < MIN_USEFUL_BYTES:
            return self._in_language(BUDGET_EXHAUSTED)

        kept = _cut_at_line(encoded, allowance - NOTICE_RESERVE_BYTES)
        notice = self._in_language(TRUNCATED_NOTICE).format(
            shown=len(kept), total=len(content)
        )
        fitted = f"{kept}\n{notice}"
        self._output_bytes_left -= len(fitted.encode())
        return fitted

    def _in_language(self, messages: dict[str, str]) -> str:
        return messages["en"] if self._language == "en" else messages["es"]


def knowledge_rows(hits: tuple[KnowledgeHit, ...]) -> list[JsonValue]:
    """Cada resultado con lo que sirve para citarlo, en filas iguales para TOON."""
    return [
        {
            "sourceType": hit.key.source_type,
            "sourceId": hit.key.source_id,
            "score": round(hit.score, 3),
            "text": hit.text,
        }
        for hit in hits
    ]


def _cut_at_line(encoded: bytes, limit: int) -> str:
    text = encoded[:limit].decode(errors="ignore")
    last_line_end = text.rfind("\n")
    if last_line_end > 0:
        return text[:last_line_end]
    return text


def _single_text_argument(arguments: JsonObject, name: str) -> str | None:
    value = arguments.get(name)
    if set(arguments) != {name} or not isinstance(value, str):
        return None
    value = value.strip()
    if 0 < len(value) <= MAX_QUERY_LENGTH:
        return value
    return None
