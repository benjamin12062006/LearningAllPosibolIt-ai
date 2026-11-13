"""Contra un Qdrant real (`make test-qdrant`): conexión, versión y servicio entero."""

import asyncio
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl, SecretStr

from ktsu_ai.bootstrap.app import create_app
from ktsu_ai.config.configuration import (
    AuthConfiguration,
    Configuration,
    EmbeddingConfiguration,
    KnowledgeConfiguration,
    QdrantConfiguration,
    ServerConfiguration,
)
from ktsu_ai.domain.health.service_health import DependencyHealth
from ktsu_ai.infrastructure.database.qdrant.connection import create_client
from ktsu_ai.infrastructure.database.qdrant.health import QdrantProbe
from tests.support.word_hash_embedding import WordHashEmbedding

pytestmark = pytest.mark.qdrant

TOKEN = "token-de-prueba-con-32-caracteres!"
# Nadie escucha aquí: es el Qdrant «caído».
UNREACHABLE_QDRANT = "http://127.0.0.1:1"


def configuration_for(qdrant_url: str) -> Configuration:
    return Configuration(
        server=ServerConfiguration(host="127.0.0.1", port=8090, log_level="INFO"),
        auth=AuthConfiguration(service_token=SecretStr(TOKEN)),
        qdrant=QdrantConfiguration(
            url=HttpUrl(qdrant_url), api_key=None, timeout_seconds=2
        ),
        embedding=EmbeddingConfiguration(
            model="prueba",
            dimensions=64,
            batch_size=32,
            concurrency=4,
            timeout_seconds=5,
            google_cloud_project="proyecto-de-prueba",
            google_cloud_location="us-central1",
        ),
        knowledge=KnowledgeConfiguration(collection=f"prueba_{uuid.uuid4().hex}"),
    )


def qdrant_url() -> str:
    return os.environ["TEST_QDRANT_URL"]


async def check_once(url: str) -> DependencyHealth:
    client = create_client(configuration_for(url).qdrant)
    try:
        return await QdrantProbe(client).check()
    finally:
        await client.close()


def test_probe_reads_the_server_version() -> None:
    dependency = asyncio.run(check_once(qdrant_url()))

    assert dependency.available
    assert dependency.version == "1.19.1"


def test_probe_reports_an_unreachable_qdrant_without_raising() -> None:
    dependency = asyncio.run(check_once(UNREACHABLE_QDRANT))

    assert not dependency.available
    assert dependency.version is None


def test_the_whole_service_is_ready_with_qdrant_up() -> None:
    with TestClient(
        create_app(configuration_for(qdrant_url()), WordHashEmbedding())
    ) as client:
        response = client.get(
            "/v1/health", headers={"Authorization": f"Bearer {TOKEN}"}
        )

    assert response.status_code == 200
    assert response.json()["dependencies"] == [
        {"name": "qdrant", "status": "available", "version": "1.19.1"}
    ]


def test_the_whole_service_starts_and_says_503_with_qdrant_down() -> None:
    with TestClient(
        create_app(configuration_for(UNREACHABLE_QDRANT), WordHashEmbedding())
    ) as client:
        response = client.get(
            "/v1/health", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        liveness = client.get("/health")

    assert response.status_code == 503
    assert liveness.status_code == 200
