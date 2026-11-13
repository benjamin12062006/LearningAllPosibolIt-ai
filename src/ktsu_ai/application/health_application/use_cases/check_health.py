"""Caso de uso: comprobar la salud del servicio.

Flujo: `probes -> DependencyHealth[] -> ServiceHealth -> ServiceHealthOutput`.
"""

import asyncio
from collections.abc import Sequence

from ktsu_ai.application.health_application.dto_output_service_health_output import (
    ServiceHealthOutput,
)
from ktsu_ai.application.health_ports.out_dependency_probe import IDependencyProbe
from ktsu_ai.domain.health.service_health import ServiceHealth


async def execute(probes: Sequence[IDependencyProbe]) -> ServiceHealthOutput:
    # A la vez: si una dependencia tarda en no responder, las demás no esperan.
    dependencies = await asyncio.gather(*(probe.check() for probe in probes))
    health = ServiceHealth(dependencies=tuple(dependencies))
    return ServiceHealthOutput.from_domain(health)
