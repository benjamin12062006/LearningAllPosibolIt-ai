"""Una petición, con identidad y presupuesto independientes de las demás."""

import asyncio
from typing import Final

from ktsu_ai.application.agent_application.agent_toolbox import (
    MODEL_LIMIT_MESSAGE,
    TIME_LIMIT_MESSAGE,
    AgentToolbox,
)
from ktsu_ai.application.agent_application.operation_schema import validates_arguments
from ktsu_ai.application.agent_ports.out_agent_model import (
    IAgentModel,
    IOperationSelector,
    ModelTimeoutError,
    ModelTurnLimitError,
)
from ktsu_ai.application.agent_ports.out_operation_gateway import IOperationGateway
from ktsu_ai.application.knowledge_ports.in_knowledge_use_case import IKnowledgeUseCase
from ktsu_ai.domain.agent.agent_outcome import AgentOutcome
from ktsu_ai.domain.agent.agent_run import AgentOperation, AgentRun

RUN_TIMEOUT_SECONDS: Final = 120


class AgentService:
    def __init__(
        self,
        model: IAgentModel,
        gateway: IOperationGateway,
        knowledge: IKnowledgeUseCase,
        selector: IOperationSelector | None = None,
    ) -> None:
        self._model = model
        self._gateway = gateway
        self._knowledge = knowledge
        self._selector = selector

    async def run(self, run: AgentRun) -> AgentOutcome:
        toolbox: AgentToolbox | None = None
        try:
            async with asyncio.timeout(RUN_TIMEOUT_SECONDS):
                operations = await self._select(run)
                toolbox = AgentToolbox(
                    run, operations, self._gateway, self._knowledge, validates_arguments
                )
                answer = await self._model.run(run, operations, toolbox)
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


def _limited(toolbox: AgentToolbox | None, message: str) -> AgentOutcome:
    if toolbox is None:
        return AgentOutcome("limit_reached", message, ())
    return toolbox.outcome("", message)
