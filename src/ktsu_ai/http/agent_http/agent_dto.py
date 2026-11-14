"""Contrato HTTP interno de una ejecución del agente."""

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


TOKEN_PATTERN: Final = re.compile(r"[A-Za-z0-9._~+/-]{1,8192}={0,2}")


class AgentRunRequest(_Strict):
    run_id: UUID = Field(alias="runId")
    scope: AgentScopeRequest
    credential: SecretStr
    message: str = Field(min_length=1, max_length=16_000)
    history: list[AgentHistoryRequest] = Field(default_factory=list, max_length=50)
    operations: list[AgentOperationRequest] = Field(max_length=256)

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
            tuple(HistoryMessage(item.role, item.content) for item in self.history),
            tuple(operation.to_domain() for operation in self.operations),
        )
