"""Respuesta HTTP de `GET /v1/health`."""

from pydantic import BaseModel, ConfigDict

from ktsu_ai.application.health_application.dto_output_service_health_output import (
    DependencyStatus,
    ServiceHealthOutput,
)


class DependencyStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: DependencyStatus
    version: str | None


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    ready: bool
    dependencies: list[DependencyStatusResponse]

    @classmethod
    def from_output(cls, output: ServiceHealthOutput) -> "HealthResponse":
        return cls(
            ready=output.ready,
            dependencies=[
                DependencyStatusResponse(
                    name=dependency.name,
                    status=dependency.status,
                    version=dependency.version,
                )
                for dependency in output.dependencies
            ],
        )
