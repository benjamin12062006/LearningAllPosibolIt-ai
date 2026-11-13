"""Comprobación de salud de Qdrant (implementa `IDependencyProbe`)."""

import importlib.metadata
import logging
from typing import Final

from qdrant_client import AsyncQdrantClient

from ktsu_ai.domain.health.service_health import DependencyHealth

QDRANT_DEPENDENCY: Final = "qdrant"

# La regla de compatibilidad del propio cliente: misma versión mayor y como
# mucho una versión menor de diferencia.
MAX_MINOR_VERSION_DISTANCE: Final = 1

logger = logging.getLogger(__name__)


class QdrantProbe:
    def __init__(self, client: AsyncQdrantClient) -> None:
        self._client = client

    async def check(self) -> DependencyHealth:
        """Disponible si responde con una versión compatible con el cliente."""
        server_version = await self._server_version()
        if server_version is None:
            return DependencyHealth(name=QDRANT_DEPENDENCY, available=False)

        compatible = is_compatible_with_client(server_version)
        if not compatible:
            logger.warning(
                "Qdrant %s no es compatible con qdrant-client %s",
                server_version,
                client_version(),
            )
        return DependencyHealth(
            name=QDRANT_DEPENDENCY,
            available=compatible,
            version=server_version,
        )

    async def _server_version(self) -> str | None:
        try:
            info = await self._client.info()
        except Exception as error:
            # Solo el tipo: el mensaje podría llevar la URL con la clave de API.
            logger.warning("Qdrant no responde: %s", type(error).__name__)
            return None
        return info.version


def is_compatible_with_client(server_version: str) -> bool:
    server = _major_minor(server_version)
    client = _major_minor(client_version())
    if server is None or client is None:
        return False
    same_major = server[0] == client[0]
    close_minor = abs(server[1] - client[1]) <= MAX_MINOR_VERSION_DISTANCE
    return same_major and close_minor


def client_version() -> str:
    return importlib.metadata.version("qdrant-client")


def _major_minor(version: str) -> tuple[int, int] | None:
    """`1.19.1` → `(1, 19)`; `None` si no tiene esa forma."""
    parts = version.split(".")
    if len(parts) < 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        return None
    return int(parts[0]), int(parts[1])
