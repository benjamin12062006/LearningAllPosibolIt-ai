"""Lo que un cliente MCP externo puede pedirle a Nest (plan 04 del agente, D2 a D4).

Nest decide qué operaciones se ofrecen y con qué permisos: aquí solo se
transportan su catálogo, las lecturas y las propuestas pendientes de una persona.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from ktsu_ai.domain.agent.agent_run import JsonObject, JsonValue


class IntegrationRejectedError(Exception):
    """Mensaje público de Nest o traducción local de un fallo de transporte."""

    def __init__(
        self, message: str, status: int | None = None, code: str | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


@dataclass(frozen=True, slots=True)
class IntegrationOperation:
    name: str
    description: str
    input_schema: JsonObject
    # Una lectura se ejecuta; una escritura solo se prepara para confirmarla.
    level: Literal["read", "write"]


class IIntegrationGateway(Protocol):
    async def operations(self) -> tuple[IntegrationOperation, ...]: ...

    async def call(
        self, operation: IntegrationOperation, arguments: JsonObject
    ) -> JsonValue: ...
