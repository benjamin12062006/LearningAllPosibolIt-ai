"""Fachada de aplicación para la salud.

`HealthService` implementa el puerto de entrada (`IHealthUseCase`) y delega en
`use_cases`, como `UserService` en la referencia de arquitectura.
"""

from collections.abc import Sequence

from ktsu_ai.application.health_application.dto_output_service_health_output import (
    ServiceHealthOutput,
)
from ktsu_ai.application.health_application.use_cases import check_health
from ktsu_ai.application.health_ports.out_dependency_probe import IDependencyProbe


class HealthService:
    def __init__(self, probes: Sequence[IDependencyProbe]) -> None:
        self._probes = tuple(probes)

    async def check_health(self) -> ServiceHealthOutput:
        return await check_health.execute(self._probes)
