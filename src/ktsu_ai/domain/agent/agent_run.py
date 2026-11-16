"""Contrato del turno que Nest entrega al servicio de IA."""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final, Literal

from ktsu_ai.domain.access.access_scope import AccessScope

type JsonValue = (
    str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
)
type JsonObject = dict[str, JsonValue]

SEARCH_KNOWLEDGE: Final = "search_knowledge"
ASK_FOR_CLARIFICATION: Final = "ask_for_clarification"
RESERVED_TOOL_NAMES: Final = frozenset(
    {SEARCH_KNOWLEDGE, ASK_FOR_CLARIFICATION, "handoff"}
)
OPERATION_NAME: Final = re.compile(r"[a-z][a-z0-9_]{2,63}")


class OperationLevel(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class AgentOperation:
    name: str
    description: str
    input_schema: JsonObject
    level: OperationLevel


@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    scope: AccessScope
    credential: str = field(repr=False)


@dataclass(frozen=True)
class HistoryMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class RunContext:
    """Dónde trabaja la persona: lo fija Nest con IDs ya autorizados."""

    workbook_id: str | None = None
    worksheet_id: str | None = None
    revision_id: str | None = None
    selection_id: str | None = None
    section: str | None = None
    catalog_snapshot_id: str | None = None
    evaluation_id: str | None = None
    ruleset_revision: int | None = None
    language: Literal["en", "es"] | None = None


@dataclass(frozen=True)
class AgentRun:
    identity: RunIdentity
    message: str
    history: tuple[HistoryMessage, ...]
    operations: tuple[AgentOperation, ...]
    context: RunContext = field(default_factory=RunContext)

    def __post_init__(self) -> None:
        names: set[str] = set()
        for operation in self.operations:
            name = operation.name
            if not OPERATION_NAME.fullmatch(name) or name in RESERVED_TOOL_NAMES:
                raise ValueError("Nombre de operación inválido o reservado.")
            if name in names:
                raise ValueError("El catálogo contiene una operación repetida.")
            names.add(name)
