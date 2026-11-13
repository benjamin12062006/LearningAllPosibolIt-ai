"""Puerto de entrada: lo que la aplicación ofrece sobre su salud."""

from typing import Protocol

from ktsu_ai.application.health_application.dto_output_service_health_output import (
    ServiceHealthOutput,
)


class IHealthUseCase(Protocol):
    async def check_health(self) -> ServiceHealthOutput: ...
