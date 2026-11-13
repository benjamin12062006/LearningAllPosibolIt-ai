"""Rutas de conocimiento con el middleware real y un caso de uso simulado."""

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ktsu_ai.application.knowledge_application.dto_input_replace_source_input import (
    ReplaceSourceInput,
)
from ktsu_ai.application.knowledge_application.dto_input_search_knowledge_input import (
    SearchKnowledgeInput,
)
from ktsu_ai.application.knowledge_application.dto_output_replace_source_output import (
    ReplaceSourceOutput,
)
from ktsu_ai.application.knowledge_application.dto_output_search_knowledge_output import (
    SearchKnowledgeOutput,
)
from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.domain.knowledge.knowledge_document import (
    KnowledgeHit,
    SourceKey,
    SourceType,
)
from ktsu_ai.http.middleware.internal_auth import InternalAuth
from ktsu_ai.http.routes import ApiServices, mount_routes
from tests.http.test_health_routes import FakeHealth

TOKEN = "token-de-prueba-con-32-caracteres!"
AUTHORIZED = {"Authorization": f"Bearer {TOKEN}"}
ORG = str(uuid.uuid4())
PROJECT = str(uuid.uuid4())
SOURCE_PATH = (
    f"/v1/knowledge/organizations/{ORG}/projects/{PROJECT}/sources/catalog/{PROJECT}"
)


class FakeKnowledge:
    def __init__(self) -> None:
        self.replaced: list[ReplaceSourceInput] = []
        self.removed_sources: list[SourceKey] = []
        self.removed_projects: list[tuple[str, str]] = []
        self.searches: list[SearchKnowledgeInput] = []
        self.unavailable = False

    async def replace_source(self, input: ReplaceSourceInput) -> ReplaceSourceOutput:
        self._fail_if_unavailable()
        self.replaced.append(input)
        return ReplaceSourceOutput(written=len(input.documents), unchanged=0, removed=1)

    async def remove_source(self, key: SourceKey) -> None:
        self.removed_sources.append(key)

    async def remove_project(self, organization_id: str, project_id: str) -> None:
        self.removed_projects.append((organization_id, project_id))

    async def search(self, input: SearchKnowledgeInput) -> SearchKnowledgeOutput:
        self._fail_if_unavailable()
        self.searches.append(input)
        hit = KnowledgeHit(
            key=SourceKey(ORG, PROJECT, SourceType.CATALOG, PROJECT),
            document_id="SKU-42",
            text="Zapatillas rojas",
            score=0.91,
            metadata={"outcome": "invalid", "in_feed": False},
        )
        return SearchKnowledgeOutput(hits=(hit,))

    def _fail_if_unavailable(self) -> None:
        if self.unavailable:
            raise AppError(ErrorCode.KNOWLEDGE_UNAVAILABLE)


@pytest.fixture
def knowledge() -> FakeKnowledge:
    return FakeKnowledge()


@pytest.fixture
def client(knowledge: FakeKnowledge) -> TestClient:
    app = FastAPI()
    services = ApiServices(health=FakeHealth(ready=True), knowledge=knowledge)
    mount_routes(app, services, InternalAuth(SecretStr(TOKEN)))
    return TestClient(app, raise_server_exceptions=False)


def documents_body(*ids: str, **metadata: object) -> dict[str, object]:
    return {
        "documents": [
            {
                "documentId": document_id,
                "text": f"Producto {document_id}",
                "metadata": metadata,
            }
            for document_id in ids
        ]
    }


def test_replace_source_passes_the_documents_and_answers_the_counts(
    client: TestClient, knowledge: FakeKnowledge
) -> None:
    response = client.put(
        SOURCE_PATH, headers=AUTHORIZED, json=documents_body("A", "B", outcome="valid")
    )

    assert response.status_code == 200
    assert response.json() == {"written": 2, "unchanged": 0, "removed": 1}
    replaced = knowledge.replaced[0]
    assert replaced.key == SourceKey(ORG, PROJECT, SourceType.CATALOG, PROJECT)
    assert [d.document_id for d in replaced.documents] == ["A", "B"]
    assert replaced.documents[0].metadata == {"outcome": "valid"}


@pytest.mark.parametrize(
    "body",
    [
        documents_body("A", organization_id="otra"),
        documents_body("A", document_hash="x"),
        documents_body("A", document_id="x"),
        documents_body("A", ref_doc_id="x"),
        documents_body("A", **{"Mayúscula": "x"}),
        documents_body("A", note="x" * 501),
        {"documents": [{"documentId": "", "text": "x"}]},
        {"documents": [{"documentId": "A", "text": ""}]},
        {"documents": [{"documentId": "A", "text": "x" * 8_001}]},
        {"documents": [{"documentId": "A", "text": "x", "otro": 1}]},
        {"documents": [{"documentId": "A", "text": "x", "metadata": {"a": [1]}}]},
    ],
    ids=[
        "metadato reservado de organización",
        "metadato reservado de hash",
        "metadato que escribe LlamaIndex (document_id)",
        "metadato que escribe LlamaIndex (ref_doc_id)",
        "nombre de metadato no permitido",
        "metadato demasiado largo",
        "id vacío",
        "texto vacío",
        "texto demasiado largo",
        "campo desconocido",
        "metadato que no es un valor simple",
    ],
)
def test_replace_source_validates_the_documents(
    client: TestClient, knowledge: FakeKnowledge, body: dict[str, object]
) -> None:
    response = client.put(SOURCE_PATH, headers=AUTHORIZED, json=body)

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert knowledge.replaced == []


def test_replace_source_rejects_more_documents_than_the_limit(
    client: TestClient,
) -> None:
    body = documents_body(*(f"D{n}" for n in range(5_001)))

    assert client.put(SOURCE_PATH, headers=AUTHORIZED, json=body).status_code == 400


@pytest.mark.parametrize(
    "path",
    [
        f"/v1/knowledge/organizations/no-uuid/projects/{PROJECT}/sources/catalog/{PROJECT}",
        f"/v1/knowledge/organizations/{ORG}/projects/{PROJECT}/sources/desconocido/{PROJECT}",
        f"/v1/knowledge/organizations/{ORG}/projects/{PROJECT}/sources/catalog/no-uuid",
    ],
    ids=["organización no UUID", "tipo de fuente desconocido", "fuente no UUID"],
)
def test_paths_are_validated(client: TestClient, path: str) -> None:
    response = client.put(path, headers=AUTHORIZED, json=documents_body("A"))

    assert response.status_code == 400


def test_deletes_answer_204(client: TestClient, knowledge: FakeKnowledge) -> None:
    source = client.delete(SOURCE_PATH, headers=AUTHORIZED)
    project = client.delete(
        f"/v1/knowledge/organizations/{ORG}/projects/{PROJECT}", headers=AUTHORIZED
    )

    assert (source.status_code, project.status_code) == (204, 204)
    assert source.content == b""
    assert knowledge.removed_sources == [
        SourceKey(ORG, PROJECT, SourceType.CATALOG, PROJECT)
    ]
    assert knowledge.removed_projects == [(ORG, PROJECT)]


def test_search_builds_the_scope_and_answers_in_camel_case(
    client: TestClient, knowledge: FakeKnowledge
) -> None:
    response = client.post(
        "/v1/knowledge/search",
        headers=AUTHORIZED,
        json={
            "organizationId": ORG,
            "projectIds": [PROJECT],
            "query": "  zapatillas rojas  ",
            "sourceTypes": ["catalog"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "hits": [
            {
                "projectId": PROJECT,
                "sourceType": "catalog",
                "sourceId": PROJECT,
                "documentId": "SKU-42",
                "text": "Zapatillas rojas",
                "score": 0.91,
                "metadata": {"outcome": "invalid", "in_feed": False},
            }
        ]
    }
    search = knowledge.searches[0]
    assert search.scope.organization_id == ORG
    assert search.scope.project_ids == frozenset({PROJECT})
    assert search.query == "zapatillas rojas"
    assert search.limit == 8
    assert search.source_types == frozenset({SourceType.CATALOG})


@pytest.mark.parametrize(
    "body",
    [
        {"organizationId": ORG, "projectIds": [PROJECT], "query": ""},
        {"organizationId": ORG, "projectIds": [PROJECT], "query": "x" * 1_001},
        {"organizationId": ORG, "projectIds": [PROJECT], "query": "x", "limit": 21},
        {"organizationId": "otra", "projectIds": [PROJECT], "query": "x"},
        {"organizationId": ORG, "projectIds": ["otro"], "query": "x"},
        {"projectIds": [PROJECT], "query": "x"},
    ],
    ids=[
        "pregunta vacía",
        "pregunta larga",
        "demasiados resultados",
        "organización no UUID",
        "proyecto no UUID",
        "sin organización",
    ],
)
def test_search_validates_the_body(
    client: TestClient, knowledge: FakeKnowledge, body: dict[str, object]
) -> None:
    response = client.post("/v1/knowledge/search", headers=AUTHORIZED, json=body)

    assert response.status_code == 400
    assert knowledge.searches == []


def test_every_knowledge_route_needs_the_service_token(client: TestClient) -> None:
    responses = [
        client.put(SOURCE_PATH, json=documents_body("A")),
        client.delete(SOURCE_PATH),
        client.delete(f"/v1/knowledge/organizations/{ORG}/projects/{PROJECT}"),
        client.post(
            "/v1/knowledge/search",
            json={"organizationId": ORG, "projectIds": [PROJECT], "query": "x"},
        ),
    ]

    assert [response.status_code for response in responses] == [401] * 4


def test_an_unavailable_index_answers_503(
    client: TestClient, knowledge: FakeKnowledge
) -> None:
    knowledge.unavailable = True

    response = client.put(SOURCE_PATH, headers=AUTHORIZED, json=documents_body("A"))

    assert response.status_code == 503
    assert response.json()["code"] == "KNOWLEDGE_UNAVAILABLE"
