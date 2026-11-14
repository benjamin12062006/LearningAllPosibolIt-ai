"""Nest conserva la autoridad y decide si una operación se puede realizar."""

from typing import Protocol

from ktsu_ai.domain.agent.agent_run import JsonObject, JsonValue, RunIdentity


class OperationFailedError(Exception):
    """Mensaje público de Nest o traducción local de un fallo de transporte."""


class IOperationGateway(Protocol):
    async def execute(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> JsonValue: ...

    async def prepare(
        self, identity: RunIdentity, operation: str, arguments: JsonObject
    ) -> str: ...
