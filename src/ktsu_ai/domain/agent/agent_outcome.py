"""Resultado que Nest puede guardar y mostrar al usuario."""

from dataclasses import dataclass
from typing import Literal

from ktsu_ai.domain.agent.agent_run import JsonObject

type RunStatus = Literal[
    "answered", "confirmation_required", "needs_clarification", "limit_reached"
]
type CallStatus = Literal["succeeded", "failed", "rejected", "prepared"]


@dataclass(frozen=True)
class ToolCallRecord:
    operation: str
    status: CallStatus


@dataclass(frozen=True)
class PendingConfirmation:
    operation: str
    arguments: JsonObject
    summary: str


@dataclass(frozen=True)
class AgentOutcome:
    status: RunStatus
    answer: str
    calls: tuple[ToolCallRecord, ...]
    confirmation: PendingConfirmation | None = None
