"""Construye el servicio de salud con sus comprobaciones reales."""

from qdrant_client import AsyncQdrantClient

from ktsu_ai.application.health_application.health_service import HealthService
from ktsu_ai.application.health_ports.in_health_use_case import IHealthUseCase
from ktsu_ai.infrastructure.database.qdrant.health import QdrantProbe


def build_health_service(qdrant: AsyncQdrantClient) -> IHealthUseCase:
    return HealthService(probes=[QdrantProbe(qdrant)])
