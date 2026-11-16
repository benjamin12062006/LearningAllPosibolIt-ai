"""Nest conserva la autoridad y decide si una operación se puede realizar."""

from dataclasses import dataclass
from typing import Protocol

from ktsu_ai.domain.agent.agent_run import JsonObject, JsonValue, RunIdentity


class OperationFailedError(Exception):
    """Mensaje público de Nest o traducción local de un fallo de transporte."""


@dataclass(frozen=True, slots=True)
class Preparation:
    """Lo que devuelve Nest al preparar una escritura.

    `applied` es verdadero cuando Nest la confirmó en la misma llamada
    (`AI_AUTO_CONFIRM`): entonces `result` trae el efecto y la ejecución sigue.
    Si no, queda una propuesta que la persona confirma.
    """

    summary: str
    applied: bool = False
    result: JsonValue = None


class IOperationGateway(Protocol):
    async def execute(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> JsonValue: ...

    async def prepare(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> Preparation: ...
