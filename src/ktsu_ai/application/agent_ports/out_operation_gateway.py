"""Nest conserva la autoridad y decide si una operación se puede realizar."""

from dataclasses import dataclass
from typing import Protocol

from ktsu_ai.domain.agent.agent_run import JsonObject, JsonValue, RunIdentity


class OperationFailedError(Exception):
    """Mensaje público de Nest o traducción local de un fallo de transporte.

    `str(error)` es el mensaje en español. `code` es el código público de Nest
    (nulo si el fallo es de transporte) y `english` el mismo mensaje en inglés,
    si Nest lo dio. Con el código, el modelo sabe qué corregir (ficha 12, E8).
    """

    def __init__(
        self, message: str, code: str | None = None, english: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.english = english

    def for_model(self, language: str | None) -> str:
        """El mensaje en el idioma de la ejecución, con el código delante si lo hay."""
        message = str(self)
        if language == "en" and self.english:
            message = self.english
        if self.code:
            return f"{self.code}: {message}"
        return message


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
