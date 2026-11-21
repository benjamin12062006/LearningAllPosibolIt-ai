"""Una petición, con identidad y presupuesto independientes de las demás."""

import asyncio
import logging
from typing import Final

from ktsu_ai.application.agent_application.agent_toolbox import (
    MAX_QUERY_LENGTH,
    MODEL_LIMIT_MESSAGE,
    TIME_LIMIT_MESSAGE,
    AgentToolbox,
    knowledge_rows,
)
from ktsu_ai.application.agent_application.model_text import context_notes
from ktsu_ai.application.agent_application.operation_schema import validates_arguments
from ktsu_ai.application.agent_ports.out_agent_model import (
    IAgentModel,
    IOperationSelector,
    ModelTimeoutError,
    ModelTurnLimitError,
)
from ktsu_ai.application.agent_ports.out_operation_gateway import IOperationGateway
from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_ports.in_knowledge_use_case import IKnowledgeUseCase
from ktsu_ai.common.error import AppError
from ktsu_ai.domain.agent.agent_outcome import AgentOutcome
from ktsu_ai.domain.agent.agent_run import AgentOperation, AgentRun, JsonValue

logger = logging.getLogger(__name__)

# Nest espera 210 s y reclama la ejecución 240 s (plan 10 de Nest, D2).
RUN_TIMEOUT_SECONDS: Final = 180
# La búsqueda previa es una ayuda: si tarda, el agente empieza sin ella.
PREFETCH_TIMEOUT_SECONDS: Final = 10
PREFETCH_RESULTS: Final = 6
# Los mensajes anteriores de la persona que dan sentido a «sí, hazlo» (ficha 12, C3).
PREFETCH_EARLIER_QUESTIONS: Final = 2


class AgentService:
    def __init__(
        self,
        model: IAgentModel,
        gateway: IOperationGateway,
        knowledge: IKnowledgeUseCase | None = None,
        selector: IOperationSelector | None = None,
        prefetch: IKnowledgeUseCase | None = None,
    ) -> None:
        """`knowledge` atiende `search_knowledge` aquí mismo; sin él, la pide a Nest.

        `prefetch` busca antes de llamar al modelo lo relacionado con el mensaje
        (plan 10 de Nest, D6).
        """
        self._model = model
        self._gateway = gateway
        self._knowledge = knowledge
        self._selector = selector
        self._prefetch = prefetch

    async def run(self, run: AgentRun) -> AgentOutcome:
        toolbox: AgentToolbox | None = None
        try:
            async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
                operations = await self._select(run)
                related = await self._related_knowledge(run)
                notes = context_notes(run.project, related, run.context.language)
                toolbox = AgentToolbox(
                    run, operations, self._gateway, self._knowledge, validates_arguments
                )
                answer = await self._model.run(run, operations, toolbox, notes)
                return toolbox.outcome(answer)
        except ModelTurnLimitError:
            return _limited(toolbox, MODEL_LIMIT_MESSAGE)
        except (TimeoutError, ModelTimeoutError):
            return _limited(toolbox, TIME_LIMIT_MESSAGE)

    async def _select(self, run: AgentRun) -> tuple[AgentOperation, ...]:
        if self._selector is None or not run.operations:
            return run.operations
        names = await self._selector.select(run)
        allowed = {operation.name: operation for operation in run.operations}
        return tuple(allowed[name] for name in dict.fromkeys(names) if name in allowed)

    async def _related_knowledge(self, run: AgentRun) -> list[JsonValue]:
        """Lo que Qdrant sabe del proyecto sobre lo que se pide; vacío si no responde."""
        if self._prefetch is None:
            return []
        search = SearchKnowledgeInput(
            scope=run.identity.scope,
            query=prefetch_query(run),
            limit=PREFETCH_RESULTS,
            source_types=frozenset(),
        )
        try:
            async with asyncio.timeout(PREFETCH_TIMEOUT_SECONDS):
                output = await self._prefetch.search(search)
        except (AppError, TimeoutError):
            logger.warning("Búsqueda previa sin resultados: el agente sigue sin ella")
            return []
        return knowledge_rows(output.hits)


def prefetch_query(run: AgentRun) -> str:
    """El mensaje actual con los anteriores de la persona; si sobra, se pierde lo más viejo."""
    questions = [message.content for message in run.history if message.role == "user"]
    recent = questions[-PREFETCH_EARLIER_QUESTIONS:]
    return "\n".join([*recent, run.message])[-MAX_QUERY_LENGTH:]


def _limited(toolbox: AgentToolbox | None, message: str) -> AgentOutcome:
    if toolbox is None:
        return AgentOutcome("limit_reached", message, ())
    return toolbox.outcome("", message)
