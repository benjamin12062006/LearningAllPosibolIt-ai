"""Construcción del cliente de Qdrant.

Cliente oficial asíncrono por REST (puerto 6333 dentro del contenedor, 56333 en
desarrollo).
"""

from qdrant_client import AsyncQdrantClient

from ktsu_ai.config.configuration import QdrantConfiguration


def create_client(config: QdrantConfiguration) -> AsyncQdrantClient:
    api_key = config.api_key.get_secret_value() if config.api_key else None
    return AsyncQdrantClient(
        url=str(config.url),
        api_key=api_key,
        timeout=config.timeout_seconds,
        # Sin gRPC: una sola vía de conexión, la misma que usa la consola web.
        prefer_grpc=False,
        # Su comprobación de versión es una petición síncrona al crear el cliente:
        # con Qdrant caído bloquearía el arranque. La hace `QdrantProbe`.
        check_compatibility=False,
    )
