"""Contrato HTTP interno de una ejecución del agente."""

import json
import re
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ktsu_ai.application.agent_application.operation_schema import (
    check_operation_schema,
)
from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.agent.agent_run import (
    AgentOperation,
    AgentRun,
    HistoryMessage,
    JsonObject,
    OperationLevel,
    RunContext,
    RunIdentity,
)
from ktsu_ai.http.knowledge_http.dto.knowledge_request_dto import KnowledgeLimits


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class AgentScopeRequest(_Strict):
    organization_id: UUID = Field(alias="organizationId")
    project_ids: list[UUID] = Field(
        alias="projectIds", max_length=KnowledgeLimits.MAX_VISIBLE_PROJECTS
    )

    def to_domain(self) -> AccessScope:
        return AccessScope(
            str(self.organization_id),
            frozenset(str(project_id) for project_id in self.project_ids),
        )


class AgentOperationRequest(_Strict):
    name: str
    description: str = Field(min_length=1, max_length=1_024)
    input_schema: JsonObject = Field(alias="inputSchema")
    level: OperationLevel

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(cls, schema: JsonObject) -> JsonObject:
        check_operation_schema(schema)
        return schema

    def to_domain(self) -> AgentOperation:
        return AgentOperation(
            self.name, self.description, self.input_schema, self.level
        )


class AgentHistoryRequest(_Strict):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=16_000)
    activity: JsonObject | None = None

    @field_validator("activity")
    @classmethod
    def validate_activity_size(cls, activity: JsonObject | None) -> JsonObject | None:
        # Nest acota el historial entero; esto solo frena un cuerpo anómalo.
        if activity is not None and len(json.dumps(activity)) > MAX_ACTIVITY_BYTES:
            raise ValueError("La actividad de un mensaje es demasiado grande.")
        return activity


class AgentContextRequest(_Strict):
    """Contexto de la ejecución que manda Nest (E6.3a): solo IDs autorizados."""

    workbook_id: UUID | None = Field(default=None, alias="workbookId")
    worksheet_id: UUID | None = Field(default=None, alias="worksheetId")
    revision_id: UUID | None = Field(default=None, alias="revisionId")
    selection_id: UUID | None = Field(default=None, alias="selectionId")
    section: (
        Literal[
            "project",
            "catalog",
            "rules",
            "evaluations",
            "products",
            "feed",
            "worksheets",
            "integrations",
            "chats",
        ]
        | None
    ) = None
    catalog_snapshot_id: UUID | None = Field(default=None, alias="catalogSnapshotId")
    evaluation_id: UUID | None = Field(default=None, alias="evaluationId")
    ruleset_revision: int | None = Field(default=None, alias="rulesetRevision", ge=1)
    language: Literal["en", "es"] | None = None

    def to_domain(self) -> RunContext:
        def text(value: UUID | None) -> str | None:
            return None if value is None else str(value)

        return RunContext(
            text(self.workbook_id),
            text(self.worksheet_id),
            text(self.revision_id),
            text(self.selection_id),
            self.section,
            text(self.catalog_snapshot_id),
            text(self.evaluation_id),
            self.ruleset_revision,
            self.language,
        )


TOKEN_PATTERN: Final = re.compile(r"[A-Za-z0-9._~+/-]{1,8192}={0,2}")
MAX_ACTIVITY_BYTES: Final = 64 * 1024
MAX_PROJECT_BYTES: Final = 128 * 1024


class AgentRunRequest(_Strict):
    run_id: UUID = Field(alias="runId")
    scope: AgentScopeRequest
    credential: SecretStr
    message: str = Field(min_length=1, max_length=16_000)
    # Igual que `AGENT_RUN_LIMITS.historyMessages` de Nest (plan 10, D2).
    history: list[AgentHistoryRequest] = Field(default_factory=list, max_length=100)
    omitted_messages: int = Field(default=0, alias="omittedMessages", ge=0)
    project: JsonObject | None = None

    @field_validator("project")
    @classmethod
    def validate_project_size(cls, project: JsonObject | None) -> JsonObject | None:
        # Nest acota la ficha; esto solo frena un cuerpo anómalo.
        if project is not None and len(json.dumps(project)) > MAX_PROJECT_BYTES:
            raise ValueError("La ficha del proyecto es demasiado grande.")
        return project

    operations: list[AgentOperationRequest] = Field(max_length=256)
    context: AgentContextRequest = Field(default_factory=AgentContextRequest)

    @field_validator("credential", mode="before")
    @classmethod
    def validate_bearer(cls, value: object) -> str:
        if not isinstance(value, str) or not TOKEN_PATTERN.fullmatch(value):
            raise ValueError("Credencial de ejecución inválida.")
        return value

    def to_domain(self) -> AgentRun:
        identity = RunIdentity(
            str(self.run_id), self.scope.to_domain(), self.credential.get_secret_value()
        )
        return AgentRun(
            identity,
            self.message,
            tuple(
                HistoryMessage(item.role, item.content, item.activity)
                for item in self.history
            ),
            tuple(operation.to_domain() for operation in self.operations),
            self.context.to_domain(),
            self.omitted_messages,
            self.project,
        )
