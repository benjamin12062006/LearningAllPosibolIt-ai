"""Recurso Qdrant: el cliente que comparten las features.

A diferencia de la referencia (que no arranca sin base), aquí Qdrant puede
faltar: el servicio arranca igual y `/v1/health` lo dice (plan 01, S6).
"""

import logging

from qdrant_client import AsyncQdrantClient

from ktsu_ai.infrastructure.database.qdrant.health import QdrantProbe

logger = logging.getLogger(__name__)


async def report_availability(client: AsyncQdrantClient) -> None:
    """Deja en el registro si Qdrant respondió al arrancar; no impide arrancar."""
    dependency = await QdrantProbe(client).check()
    if dependency.available:
        logger.info("Qdrant %s disponible", dependency.version)
    else:
        logger.warning("Qdrant no disponible al arrancar; el servicio sigue")
