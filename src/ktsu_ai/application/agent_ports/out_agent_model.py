"""Ejecución del modelo y selección de operaciones para una petición."""

from typing import Protocol

from ktsu_ai.application.agent_application.agent_toolbox import AgentToolbox
from ktsu_ai.domain.agent.agent_run import AgentOperation, AgentRun


class ModelTurnLimitError(Exception):
    """El modelo agotó su presupuesto de turnos."""


class ModelTimeoutError(Exception):
    """El modelo agotó el plazo de la ejecución."""


class IAgentModel(Protocol):
    async def run(
        self,
        run: AgentRun,
        operations: tuple[AgentOperation, ...],
        toolbox: AgentToolbox,
        notes: str = "",
    ) -> str:
        """`notes`: ficha del proyecto y conocimiento relacionado, ya en texto."""
        ...


class IOperationSelector(Protocol):
    async def select(self, run: AgentRun) -> tuple[str, ...]: ...
