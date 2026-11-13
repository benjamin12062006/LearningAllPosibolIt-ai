"""Salida del caso de uso de salud, tal como la verá quien llame al servicio."""

from dataclasses import dataclass
from typing import Literal

from ktsu_ai.domain.health.service_health import DependencyHealth, ServiceHealth

type DependencyStatus = Literal["available", "unavailable"]


@dataclass(frozen=True)
class DependencyStatusOutput:
    name: str
    status: DependencyStatus
    version: str | None

    @classmethod
    def from_domain(cls, dependency: DependencyHealth) -> "DependencyStatusOutput":
        status: DependencyStatus = (
            "available" if dependency.available else "unavailable"
        )
        return cls(name=dependency.name, status=status, version=dependency.version)


@dataclass(frozen=True)
class ServiceHealthOutput:
    ready: bool
    dependencies: tuple[DependencyStatusOutput, ...]

    @classmethod
    def from_domain(cls, health: ServiceHealth) -> "ServiceHealthOutput":
        return cls(
            ready=health.is_ready,
            dependencies=tuple(
                DependencyStatusOutput.from_domain(dependency)
                for dependency in health.dependencies
            ),
        )
