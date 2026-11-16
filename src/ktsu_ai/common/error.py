"""Errores públicos del servicio, con la misma forma que la API Nest.

El cuerpo de error es `{ code, message: { es, en }, requestId }` (plan 01, S8):
Nest puede leer los errores de este servicio igual que los suyos.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class ErrorCode(StrEnum):
    """Códigos estables: un cliente puede decidir por ellos. Solo se añaden al final."""

    AUTH_SERVICE_TOKEN_INVALID = "AUTH_SERVICE_TOKEN_INVALID"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    KNOWLEDGE_DOCUMENT_DUPLICATED = "KNOWLEDGE_DOCUMENT_DUPLICATED"
    KNOWLEDGE_UNAVAILABLE = "KNOWLEDGE_UNAVAILABLE"
    AGENT_UNAVAILABLE = "AGENT_UNAVAILABLE"
    AGENT_MODEL_RATE_LIMITED = "AGENT_MODEL_RATE_LIMITED"


@dataclass(frozen=True)
class LocalizedMessage:
    es: str
    en: str


@dataclass(frozen=True)
class ErrorDefinition:
    status: int
    message: LocalizedMessage


ERRORS: Final[dict[ErrorCode, ErrorDefinition]] = {
    ErrorCode.AUTH_SERVICE_TOKEN_INVALID: ErrorDefinition(
        401,
        LocalizedMessage(
            es="Falta el token del servicio o no es válido.",
            en="The service token is missing or invalid.",
        ),
    ),
    ErrorCode.VALIDATION_FAILED: ErrorDefinition(
        400,
        LocalizedMessage(
            es="Revisa los datos enviados.",
            en="Review the submitted data.",
        ),
    ),
    ErrorCode.ROUTE_NOT_FOUND: ErrorDefinition(
        404,
        LocalizedMessage(
            es="La ruta no existe.",
            en="The route does not exist.",
        ),
    ),
    ErrorCode.INTERNAL_ERROR: ErrorDefinition(
        500,
        LocalizedMessage(
            es="Error interno del servicio de IA.",
            en="Internal error in the AI service.",
        ),
    ),
    ErrorCode.KNOWLEDGE_DOCUMENT_DUPLICATED: ErrorDefinition(
        400,
        LocalizedMessage(
            es="Dos documentos de la misma fuente tienen el mismo id.",
            en="Two documents of the same source have the same id.",
        ),
    ),
    ErrorCode.KNOWLEDGE_UNAVAILABLE: ErrorDefinition(
        503,
        LocalizedMessage(
            es="El índice de conocimiento no está disponible ahora. Reinténtalo.",
            en="The knowledge index is not available right now. Try again.",
        ),
    ),
    ErrorCode.AGENT_UNAVAILABLE: ErrorDefinition(
        503,
        LocalizedMessage(
            es="El agente de IA no está disponible ahora.",
            en="The AI agent is currently unavailable.",
        ),
    ),
    ErrorCode.AGENT_MODEL_RATE_LIMITED: ErrorDefinition(
        429,
        LocalizedMessage(
            es="Gemini está limitando las solicitudes.",
            en="Gemini is rate-limiting requests.",
        ),
    ),
}


class AppError(Exception):
    """Un error que el servicio sabe explicar a quien lo llama."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code.value)
        self.code = code

    @property
    def definition(self) -> ErrorDefinition:
        return ERRORS[self.code]
