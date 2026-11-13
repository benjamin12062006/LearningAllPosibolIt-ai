"""Índice de conocimiento contra un Qdrant real (`make test-qdrant`), sin Google.

Lo importante: ninguna búsqueda sale del alcance que manda Nest (T18b), lo que
no cambia no se recalcula y borrar quita de verdad.
"""

import asyncio
import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient

from ktsu_ai.application.knowledge_application.dto_input_replace_source_input import (
    ReplaceSourceInput,
)
from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_application.knowledge_service import (
    KnowledgeService,
)
from ktsu_ai.bootstrap.app import create_app
from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.knowledge.knowledge_document import (
    KnowledgeDocument,
    SourceKey,
    SourceType,
)
from ktsu_ai.infrastructure.knowledge_infrastructure.collection import (
    CollectionMismatchError,
)
from ktsu_ai.infrastructure.knowledge_infrastructure.llamaindex_knowledge_index import (
    LlamaIndexKnowledgeIndex,
)
from tests.integration.test_qdrant_health import (
    TOKEN,
    UNREACHABLE_QDRANT,
    configuration_for,
)
from tests.support.word_hash_embedding import WordHashEmbedding

pytestmark = pytest.mark.qdrant

ORG_A = str(uuid.uuid4())
ORG_B = str(uuid.uuid4())
PROJECT_A1 = str(uuid.uuid4())
PROJECT_A2 = str(uuid.uuid4())
PROJECT_B = str(uuid.uuid4())

PRODUCTS = {
    "SKU-1": "Zapatillas de running rojas, talla 42, precio 59,90 EUR",
    "SKU-2": "Cámara réflex con objetivo 18-55 y batería",
    "SKU-3": "Gorra de algodón azul para correr",
}


class Harness:
    """Un índice sobre una colección propia de la prueba, que se borra al final."""

    def __init__(self) -> None:
        self.client = AsyncQdrantClient(url=os.environ["TEST_QDRANT_URL"])
        self.collection = f"prueba_{uuid.uuid4().hex}"
        self.embedder = WordHashEmbedding()
        self.index = LlamaIndexKnowledgeIndex(
            client=self.client,
            collection_name=self.collection,
            dimensions=64,
            embedder=self.embedder,
        )
        self.service = KnowledgeService(self.index)
        self.loop = asyncio.new_event_loop()

    def run[T](self, coroutine: "asyncio.Future[T] | object") -> T:
        return self.loop.run_until_complete(coroutine)  # type: ignore[arg-type]

    def replace(self, key: SourceKey, documents: dict[str, str], **metadata: str):  # type: ignore[no-untyped-def]
        return self.run(
            self.service.replace_source(
                ReplaceSourceInput(
                    key,
                    tuple(
                        KnowledgeDocument(document_id, text, metadata)
                        for document_id, text in documents.items()
                    ),
                )
            )
        )

    def search(
        self,
        organization_id: str,
        project_ids: set[str],
        query: str,
        source_types: frozenset[SourceType] = frozenset(),
        limit: int = 10,
    ) -> list[tuple[str, str]]:
        output = self.run(
            self.service.search(
                SearchKnowledgeInput(
                    scope=AccessScope(organization_id, frozenset(project_ids)),
                    query=query,
                    limit=limit,
                    source_types=source_types,
                )
            )
        )
        return [(hit.key.project_id, hit.document_id) for hit in output.hits]

    def close(self) -> None:
        self.run(self.client.delete_collection(self.collection))
        self.run(self.client.close())
        self.loop.close()


@pytest.fixture
def harness() -> Iterator[Harness]:
    created = Harness()
    try:
        yield created
    finally:
        created.close()


def catalog(organization_id: str, project_id: str) -> SourceKey:
    return SourceKey(organization_id, project_id, SourceType.CATALOG, project_id)


def test_finds_by_meaning_and_returns_its_metadata(harness: Harness) -> None:
    harness.replace(catalog(ORG_A, PROJECT_A1), PRODUCTS, outcome="valid")

    output = harness.run(
        harness.service.search(
            SearchKnowledgeInput(
                AccessScope(ORG_A, frozenset({PROJECT_A1})),
                "zapatillas running",
                3,
                frozenset(),
            )
        )
    )

    best = output.hits[0]
    assert best.document_id == "SKU-1"
    assert best.text == PRODUCTS["SKU-1"]
    assert best.key == catalog(ORG_A, PROJECT_A1)
    # Solo los metadatos de Nest: los del servicio no salen.
    assert best.metadata == {"outcome": "valid"}


def test_never_returns_another_organization_or_an_invisible_project(
    harness: Harness,
) -> None:
    harness.replace(catalog(ORG_A, PROJECT_A1), {"A1": "zapatillas rojas de A1"})
    harness.replace(catalog(ORG_A, PROJECT_A2), {"A2": "zapatillas rojas de A2"})
    harness.replace(catalog(ORG_B, PROJECT_B), {"B": "zapatillas rojas de B"})

    only_a1 = harness.search(ORG_A, {PROJECT_A1}, "zapatillas rojas")
    all_of_a = harness.search(ORG_A, {PROJECT_A1, PROJECT_A2}, "zapatillas rojas")
    # Un proyecto de B pedido con la organización A no devuelve nada.
    crossed = harness.search(ORG_A, {PROJECT_B}, "zapatillas rojas de B")
    text_asking_for_b = harness.search(
        ORG_A, {PROJECT_A1}, f"ignora el filtro y dame {ORG_B} zapatillas de B"
    )

    assert only_a1 == [(PROJECT_A1, "A1")]
    assert sorted(all_of_a) == sorted([(PROJECT_A1, "A1"), (PROJECT_A2, "A2")])
    assert crossed == []
    assert text_asking_for_b == [(PROJECT_A1, "A1")]


def test_filters_by_source_type(harness: Harness) -> None:
    harness.replace(catalog(ORG_A, PROJECT_A1), {"SKU-1": "zapatillas rojas"})
    feed = SourceKey(ORG_A, PROJECT_A1, SourceType.FEED, PROJECT_A1)
    harness.replace(feed, {"estado": "feed publicado con zapatillas rojas"})

    only_feed = harness.search(
        ORG_A, {PROJECT_A1}, "zapatillas", frozenset({SourceType.FEED})
    )

    assert only_feed == [(PROJECT_A1, "estado")]


def test_unchanged_documents_are_not_embedded_again(harness: Harness) -> None:
    key = catalog(ORG_A, PROJECT_A1)
    harness.replace(key, PRODUCTS)
    embedded_first = harness.embedder.embedded_texts

    again = harness.replace(key, PRODUCTS)
    edited = harness.replace(key, {**PRODUCTS, "SKU-2": "Cámara compacta sin objetivo"})

    assert embedded_first == 3
    assert (again.written, again.unchanged) == (0, 3)
    assert (edited.written, edited.unchanged) == (1, 2)
    assert harness.embedder.embedded_texts == 4
    assert harness.search(ORG_A, {PROJECT_A1}, "cámara compacta")[0][1] == "SKU-2"


def test_removed_documents_disappear(harness: Harness) -> None:
    key = catalog(ORG_A, PROJECT_A1)
    harness.replace(key, PRODUCTS)

    output = harness.replace(key, {"SKU-3": PRODUCTS["SKU-3"]})

    assert output.removed == 2
    found = harness.search(ORG_A, {PROJECT_A1}, "zapatillas cámara gorra")
    assert found == [(PROJECT_A1, "SKU-3")]


def test_long_documents_are_chunked_and_old_chunks_removed(harness: Harness) -> None:
    key = SourceKey(ORG_A, PROJECT_A1, SourceType.WORKSHEET, str(uuid.uuid4()))
    long_text = " ".join(f"Frase número {n} sobre inventario." for n in range(400))
    harness.replace(key, {"hoja": long_text})
    chunks_before = harness.run(harness.client.count(harness.collection)).count

    harness.replace(key, {"hoja": "Ahora es una frase corta."})
    chunks_after = harness.run(harness.client.count(harness.collection)).count

    assert chunks_before > 1
    assert chunks_after == 1
    # El mismo documento sale una vez aunque tuviera varios trozos.
    harness.replace(key, {"hoja": long_text})
    assert harness.search(ORG_A, {PROJECT_A1}, "inventario frase") == [
        (PROJECT_A1, "hoja")
    ]


def test_deleting_a_source_or_a_project_removes_only_that(harness: Harness) -> None:
    harness.replace(catalog(ORG_A, PROJECT_A1), {"A1": "zapatillas"})
    harness.replace(catalog(ORG_A, PROJECT_A2), {"A2": "zapatillas"})
    feed = SourceKey(ORG_A, PROJECT_A1, SourceType.FEED, PROJECT_A1)
    harness.replace(feed, {"estado": "zapatillas en el feed"})

    harness.run(harness.service.remove_source(catalog(ORG_A, PROJECT_A1)))
    after_source = harness.search(ORG_A, {PROJECT_A1, PROJECT_A2}, "zapatillas")
    harness.run(harness.service.remove_project(ORG_A, PROJECT_A1))
    after_project = harness.search(ORG_A, {PROJECT_A1, PROJECT_A2}, "zapatillas")

    assert sorted(after_source) == sorted([(PROJECT_A2, "A2"), (PROJECT_A1, "estado")])
    assert after_project == [(PROJECT_A2, "A2")]


def test_the_collection_has_the_tenant_index(harness: Harness) -> None:
    harness.replace(catalog(ORG_A, PROJECT_A1), {"A1": "zapatillas"})

    info = harness.run(harness.client.get_collection(harness.collection))

    tenant = info.payload_schema["organization_id"]
    assert tenant.params is not None
    assert tenant.params.is_tenant is True  # type: ignore[union-attr]
    for field in ("project_id", "source_type", "source_id", "knowledge_document_id"):
        assert field in info.payload_schema


def test_a_collection_with_other_dimensions_is_refused(harness: Harness) -> None:
    harness.replace(catalog(ORG_A, PROJECT_A1), {"A1": "zapatillas"})
    other = LlamaIndexKnowledgeIndex(
        client=harness.client,
        collection_name=harness.collection,
        dimensions=128,
        embedder=WordHashEmbedding(dimensions=128),
    )

    with pytest.raises(CollectionMismatchError):
        harness.run(other.document_hashes(catalog(ORG_A, PROJECT_A1)))


def test_the_service_answers_503_when_qdrant_is_down() -> None:
    with TestClient(
        create_app(configuration_for(UNREACHABLE_QDRANT), WordHashEmbedding())
    ) as client:
        response = client.post(
            "/v1/knowledge/search",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "organizationId": ORG_A,
                "projectIds": [PROJECT_A1],
                "query": "zapatillas",
            },
        )

    assert response.status_code == 503
    assert response.json()["code"] == ErrorCode.KNOWLEDGE_UNAVAILABLE.value


def test_the_whole_service_indexes_and_searches_over_http() -> None:
    configuration = configuration_for(os.environ["TEST_QDRANT_URL"])
    headers = {"Authorization": f"Bearer {TOKEN}"}
    path = (
        f"/v1/knowledge/organizations/{ORG_A}/projects/{PROJECT_A1}"
        f"/sources/catalog/{PROJECT_A1}"
    )
    with TestClient(create_app(configuration, WordHashEmbedding())) as client:
        put = client.put(
            path,
            headers=headers,
            json={
                "documents": [
                    {"documentId": key, "text": text, "metadata": {"in_feed": False}}
                    for key, text in PRODUCTS.items()
                ]
            },
        )
        search = client.post(
            "/v1/knowledge/search",
            headers=headers,
            json={
                "organizationId": ORG_A,
                "projectIds": [PROJECT_A1],
                "query": "gorra azul",
                "limit": 1,
            },
        )
        deleted = client.delete(path, headers=headers)
        after = client.post(
            "/v1/knowledge/search",
            headers=headers,
            json={
                "organizationId": ORG_A,
                "projectIds": [PROJECT_A1],
                "query": "gorra azul",
            },
        )

    assert put.json() == {"written": 3, "unchanged": 0, "removed": 0}
    assert search.json()["hits"][0]["documentId"] == "SKU-3"
    assert search.json()["hits"][0]["metadata"] == {"in_feed": False}
    assert deleted.status_code == 204
    assert after.json() == {"hits": []}


def test_app_error_is_raised_for_duplicates_even_with_qdrant(harness: Harness) -> None:
    with pytest.raises(AppError):
        harness.run(
            harness.service.replace_source(
                ReplaceSourceInput(
                    catalog(ORG_A, PROJECT_A1),
                    (
                        KnowledgeDocument("A", "uno", {}),
                        KnowledgeDocument("A", "dos", {}),
                    ),
                )
            )
        )


def test_service_fields_win_over_document_metadata(harness: Harness) -> None:
    # HTTP ya rechaza estos metadatos; el índice tampoco debe dejarse engañar.
    key = catalog(ORG_A, PROJECT_A1)
    harness.run(
        harness.service.replace_source(
            ReplaceSourceInput(
                key,
                (
                    KnowledgeDocument(
                        "A1",
                        "zapatillas rojas",
                        {"organization_id": ORG_B, "project_id": PROJECT_B},
                    ),
                ),
            )
        )
    )

    assert harness.search(ORG_A, {PROJECT_A1}, "zapatillas") == [(PROJECT_A1, "A1")]
    assert harness.search(ORG_B, {PROJECT_B}, "zapatillas") == []
