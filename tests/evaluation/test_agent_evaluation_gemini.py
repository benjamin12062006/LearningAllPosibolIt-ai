"""Los mismos casos con Gemini real por Vertex AI (plan 03 del agente, G6 y G7).

Cuesta dinero: solo con `make eval-gemini`. El modelo elige sus llamadas. Los
criterios duros (seguridad y alcance) hacen fallar la prueba; los de calidad,
la latencia y el coste se resumen en una tabla al terminar.
"""

from __future__ import annotations

import asyncio
import json
import time
import unicodedata
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any, Final

import pytest
from llama_index.core.instrumentation import get_dispatcher
from llama_index.core.instrumentation.event_handlers import BaseEventHandler
from llama_index.core.instrumentation.events import BaseEvent
from llama_index.core.instrumentation.events.llm import LLMChatEndEvent
from llama_index.core.llms.function_calling import FunctionCallingLLM

from ktsu_ai.application.agent_application.agent_service import AgentService
from ktsu_ai.config.loader import load_configuration
from ktsu_ai.domain.agent.agent_outcome import AgentOutcome
from ktsu_ai.domain.agent.agent_run import OperationLevel
from ktsu_ai.infrastructure.agent_infrastructure.gemini_chat_model import (
    create_gemini_chat_model,
)
from ktsu_ai.infrastructure.agent_infrastructure.llamaindex_agent import LlamaIndexAgent
from tests.evaluation.dataset import (
    DATASET,
    OPERATIONS,
    SCOPE,
    EvaluationCase,
    EvaluationGateway,
    knowledge_for,
)

# Precio de Vertex AI para gemini-3.5-flash-lite en `global`, consultado el
# 2026-11-13 (ficha 03, F2). La salida incluye el razonamiento.
INPUT_USD_PER_MILLION: Final = 0.30
OUTPUT_USD_PER_MILLION: Final = 2.50
REAL_MODEL_CASES: Final = [case for case in DATASET.cases if not case.scripted_only]

pytestmark = [
    pytest.mark.gemini,
    pytest.mark.filterwarnings(
        "ignore:Payload indexes have no effect in the local Qdrant"
    ),
]


@dataclass
class Usage:
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    tool_outputs: list[str] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        billed_output = self.output_tokens + self.thinking_tokens
        return (
            self.input_tokens * INPUT_USD_PER_MILLION
            + billed_output * OUTPUT_USD_PER_MILLION
        ) / 1_000_000


class UsageRecorder(BaseEventHandler):
    """Suma los tokens de cada respuesta de Gemini y guarda lo que vio el modelo."""

    usage: Usage = Usage()

    @classmethod
    def class_name(cls) -> str:
        return "UsageRecorder"

    def handle(self, event: BaseEvent, **kwargs: Any) -> None:
        if not isinstance(event, LLMChatEndEvent) or event.response is None:
            return
        metadata = (event.response.raw or {}).get("usage_metadata") or {}
        self.usage.model_calls += 1
        self.usage.input_tokens += metadata.get("prompt_token_count") or 0
        self.usage.output_tokens += metadata.get("candidates_token_count") or 0
        self.usage.thinking_tokens += metadata.get("thoughts_token_count") or 0
        self.usage.tool_outputs = [
            message.content or ""
            for message in event.messages
            if message.role == "tool"
        ]


@dataclass(frozen=True)
class CaseReport:
    case: str
    expected_status: str
    status: str
    status_ok: bool
    calls_ok: bool
    answer_hits: str
    seconds: float
    model_calls: int
    input_tokens: int
    output_tokens: int
    thinking_tokens: int
    cost_usd: float
    calls: list[str]
    answer: str


@pytest.fixture(scope="module")
def gemini() -> FunctionCallingLLM:
    chat = load_configuration().chat
    if chat is None:
        pytest.skip("CHAT_MODEL está vacío en el .env.")
    return create_gemini_chat_model(chat)


@pytest.fixture(scope="module")
def recorder() -> Iterator[UsageRecorder]:
    handler = UsageRecorder()
    dispatcher = get_dispatcher()
    dispatcher.add_event_handler(handler)
    yield handler
    dispatcher.event_handlers.remove(handler)


@pytest.fixture(scope="module")
def reports() -> Iterator[list[CaseReport]]:
    collected: list[CaseReport] = []
    yield collected
    _print_summary(collected)


@pytest.mark.parametrize("case", REAL_MODEL_CASES, ids=lambda case: case.id)
def test_gemini_keeps_the_hard_rules(
    case: EvaluationCase,
    gemini: FunctionCallingLLM,
    recorder: UsageRecorder,
    reports: list[CaseReport],
) -> None:
    recorder.usage = Usage()
    gateway = EvaluationGateway(case.identity(), case.gateway)

    start = time.perf_counter()
    outcome, queries = asyncio.run(_run(case, gemini, gateway))
    seconds = time.perf_counter() - start

    reports.append(_report(case, outcome, recorder.usage, seconds))
    _assert_hard_rules(case, outcome, gateway, queries, recorder.usage)


async def _run(
    case: EvaluationCase, gemini: FunctionCallingLLM, gateway: EvaluationGateway
) -> tuple[AgentOutcome, list[Any]]:
    async with knowledge_for(case) as knowledge:
        service = AgentService(LlamaIndexAgent(gemini), gateway, knowledge)
        outcome = await service.run(case.run())
        return outcome, list(knowledge.queries)


def _assert_hard_rules(
    case: EvaluationCase,
    outcome: AgentOutcome,
    gateway: EvaluationGateway,
    queries: list[Any],
    usage: Usage,
) -> None:
    """Lo que nunca puede pasar, conteste mejor o peor el modelo (doc. 15)."""
    for call in gateway.calls:
        assert call.operation in case.offers, f"Fuera del catálogo: {call}"
        operation = OPERATIONS[call.operation]
        if operation.level is OperationLevel.WRITE:
            assert call.mode == "prepare", f"Escritura ejecutada: {call}"
    assert gateway.foreign_identities == []
    assert all(query.scope == SCOPE for query in queries)
    if outcome.confirmation is not None:
        prepared = [reply for reply in case.gateway if reply.mode == "prepare"]
        assert outcome.confirmation.summary in [reply.summary for reply in prepared]
    for text in case.expected.tool_output_excludes:
        assert text not in outcome.answer
        assert all(text not in output for output in usage.tool_outputs)


def _report(
    case: EvaluationCase, outcome: AgentOutcome, usage: Usage, seconds: float
) -> CaseReport:
    expected = case.expected
    answer = _normalized(outcome.answer)
    hits = [text for text in expected.answer_contains if _normalized(text) in answer]
    return CaseReport(
        case=case.id,
        expected_status=expected.status,
        status=outcome.status,
        status_ok=outcome.status == expected.status,
        calls_ok=list(outcome.calls) == expected.calls,
        answer_hits=f"{len(hits)}/{len(expected.answer_contains)}",
        seconds=round(seconds, 2),
        model_calls=usage.model_calls,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        thinking_tokens=usage.thinking_tokens,
        cost_usd=usage.cost_usd,
        calls=[f"{call.operation}:{call.status}" for call in outcome.calls],
        answer=outcome.answer,
    )


def _normalized(text: str) -> str:
    """Sin mayúsculas ni tildes, y con coma decimal: «10.50» cuenta como «10,50»."""
    decomposed = unicodedata.normalize("NFD", text.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return plain.replace(".", ",")


def _print_summary(reports: list[CaseReport]) -> None:
    if not reports:
        return
    print("\n\nEvaluación con Gemini real")
    print(
        "caso | esperado | obtenido | estado | llamadas | textos | s | tokens e/s/r | $"
    )
    for row in reports:
        print(
            f"{row.case} | {row.expected_status} | {row.status} | "
            f"{'sí' if row.status_ok else 'no'} | {'sí' if row.calls_ok else 'no'} | "
            f"{row.answer_hits} | {row.seconds} | "
            f"{row.input_tokens}/{row.output_tokens}/{row.thinking_tokens} | "
            f"{row.cost_usd:.6f}"
        )
    total_cost = sum(row.cost_usd for row in reports)
    total_seconds = sum(row.seconds for row in reports)
    print(
        f"Estado esperado: {sum(row.status_ok for row in reports)}/{len(reports)} · "
        f"llamadas esperadas: {sum(row.calls_ok for row in reports)}/{len(reports)} · "
        f"tiempo total {total_seconds:.1f} s · coste total {total_cost:.6f} $"
    )
    print("Detalle:")
    for row in reports:
        print(json.dumps(asdict(row), ensure_ascii=False))
