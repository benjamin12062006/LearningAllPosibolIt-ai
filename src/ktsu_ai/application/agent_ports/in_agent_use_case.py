"""Puerto de entrada para ejecutar una petición del asistente."""

from typing import Protocol

from ktsu_ai.domain.agent.agent_outcome import AgentOutcome
from ktsu_ai.domain.agent.agent_run import AgentRun


class IAgentUseCase(Protocol):
    async def run(self, run: AgentRun) -> AgentOutcome: ...
