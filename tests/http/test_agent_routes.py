"""Ruta real y contrato de pasarela con un Nest simulado por HTTP."""

import json
from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from llama_index.core.base.llms.types import ChatMessage
from pydantic import HttpUrl
from qdrant_client import AsyncQdrantClient

from ktsu_ai.bootstrap.app import create_app
from ktsu_ai.domain.agent.agent_run import JsonObject
from tests.integration.test_qdrant_health import (
    TOKEN,
    UNREACHABLE_QDRANT,
    configuration_for,
)
from tests.support.scripted_llm import ScriptedResponses, tool_call
from tests.support.word_hash_embedding import WordHashEmbedding

PATH = "/v1/agent/runs"
AUTHORIZED = {"Authorization": f"Bearer {TOKEN}"}
RUN_ID = str(uuid4())
RUN_TOKEN = "credential-for-this-run"
NEST_PATH = f"/internal/v1/agent-runs/{RUN_ID}/operations/list_rows"


def request_body(level: str = "read") -> JsonObject:
    return {
        "runId": RUN_ID,
        "scope": {"organizationId": str(uuid4()), "projectIds": [str(uuid4())]},
        "credential": RUN_TOKEN,
        "message": "Lista las filas",
        "history": [],
        "operations": [
            {
                "name": "list_rows",
                "description": "Lista las filas",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer"}},
                    "required": ["limit"],
                    "additionalProperties": False,
                },
                "level": level,
            }
        ],
    }


@pytest.fixture
def disabled() -> Iterator[TestClient]:
    config = configuration_for(UNREACHABLE_QDRANT)
    with TestClient(create_app(config, WordHashEmbedding())) as client:
        yield client


def test_requires_service_token_before_dispatch(disabled: TestClient) -> None:
    response = disabled.post(PATH, json=request_body())

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_SERVICE_TOKEN_INVALID"


def test_returns_service_error_when_no_model_is_configured(
    disabled: TestClient,
) -> None:
    response = disabled.post(PATH, headers=AUTHORIZED, json=request_body())

    assert response.status_code == 503
    assert response.json()["code"] == "AGENT_UNAVAILABLE"


@pytest.mark.parametrize(
    "defect", ["forbidden", "duplicate", "reserved", "schema", "token"]
)
def test_invalid_run_is_rejected_before_model(
    disabled: TestClient, defect: str
) -> None:
    body = request_body()
    operations = body["operations"]
    if defect == "forbidden":
        operations[0]["level"] = "forbidden"
    elif defect == "duplicate":
        operations.append(operations[0])
    elif defect == "reserved":
        operations[0]["name"] = "ask_for_clarification"
    elif defect == "schema":
        operations[0]["inputSchema"]["properties"]["limit"]["type"] = "bad-type"
    else:
        body["credential"] = "invalid\ncredential"

    response = disabled.post(PATH, headers=AUTHORIZED, json=body)

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_FAILED"
    assert RUN_TOKEN not in response.text


@pytest.mark.parametrize(
    ("level", "nest_status", "nest_body", "status", "answer", "mode", "call_status"),
    [
        ("read", 200, {"rows": 2}, "answered", "Hay 2.", "execute", "succeeded"),
        (
            "write",
            200,
            {"summary": "Se editarán 2 filas."},
            "confirmation_required",
            "Se editarán 2 filas.",
            "prepare",
            "prepared",
        ),
        (
            "write",
            403,
            {"message": {"es": "Operación sin permiso", "en": "Forbidden"}},
            "answered",
            "Hay 2.",
            "prepare",
            "failed",
        ),
        ("write", 200, {}, "answered", "Hay 2.", "prepare", "failed"),
    ],
)
def test_runs_route_with_scripted_model_and_nest_transport(
    monkeypatch: pytest.MonkeyPatch,
    level: str,
    nest_status: int,
    nest_body: JsonObject,
    status: str,
    answer: str,
    mode: str,
    call_status: str,
) -> None:
    requests: list[httpx.Request] = []

    def nest(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(nest_status, json=nest_body)

    monkeypatch.setattr(
        "ktsu_ai.bootstrap.app.create_client",
        lambda config: AsyncQdrantClient(location=":memory:"),
    )
    config = configuration_for(UNREACHABLE_QDRANT)
    config.nest_agent_base_url = HttpUrl("http://nest.test")
    scripted = ScriptedResponses(
        tool_call("list_rows", limit=3),
        ChatMessage(role="assistant", content="Hay 2."),
    )
    app = create_app(
        config,
        WordHashEmbedding(),
        agent_llm=scripted.llm,
        nest_transport=httpx.MockTransport(nest),
    )
    with TestClient(app) as client:
        response = client.post(PATH, headers=AUTHORIZED, json=request_body(level))

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == status
    assert data["answer"] == answer
    assert data["calls"] == [{"operation": "list_rows", "status": call_status}]
    if status == "confirmation_required":
        assert data["confirmation"] == {
            "operation": "list_rows",
            "arguments": {"limit": 3},
            "summary": answer,
        }
        assert len(scripted.messages) == 1
    else:
        assert data["confirmation"] is None
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == NEST_PATH
    assert request.headers["authorization"] == f"Bearer {RUN_TOKEN}"
    assert json.loads(request.content) == {"mode": mode, "arguments": {"limit": 3}}
    assert RUN_TOKEN not in response.text
    if nest_status == 403:
        assert any(
            msg.content == "Operación sin permiso" for msg in scripted.messages[1]
        )


def test_run_accepts_the_context_from_nest_and_rejects_extra_fields(
    disabled: TestClient,
) -> None:
    body = request_body()
    body["context"] = {
        "workbookId": str(uuid4()),
        "worksheetId": str(uuid4()),
        "revisionId": None,
        "selectionId": None,
    }
    # Sin modelo configurado, un cuerpo válido llega al servicio (503).
    assert client_post(disabled, body).status_code == 503
    body["context"] = {"worksheetId": "no-es-un-uuid"}
    assert client_post(disabled, body).status_code == 400
    body["context"] = {"rows": []}
    assert client_post(disabled, body).status_code == 400


def client_post(client: TestClient, body: JsonObject) -> httpx.Response:
    return client.post(PATH, headers=AUTHORIZED, json=body)


def test_run_accepts_history_activity_and_bounds_its_size(disabled: TestClient) -> None:
    body = request_body()
    body["history"] = [
        {"role": "user", "content": "Borra duplicados"},
        {
            "role": "assistant",
            "content": "Preparé el borrador.",
            "activity": {"calls": [], "proposal": None},
        },
    ]
    body["omittedMessages"] = 2
    assert client_post(disabled, body).status_code == 503

    body["history"][1]["activity"] = {"calls": ["x" * 70_000]}
    assert client_post(disabled, body).status_code == 400
    body["history"] = [{"role": "user", "content": "hola"}] * 101
    assert client_post(disabled, body).status_code == 400
    body["history"] = []
    body["omittedMessages"] = -1
    assert client_post(disabled, body).status_code == 400


def test_history_activity_reaches_the_model_through_the_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ktsu_ai.bootstrap.app.create_client",
        lambda config: AsyncQdrantClient(location=":memory:"),
    )
    config = configuration_for(UNREACHABLE_QDRANT)
    config.nest_agent_base_url = HttpUrl("http://nest.test")
    scripted = ScriptedResponses(ChatMessage(role="assistant", content="Hecho."))
    app = create_app(
        config,
        WordHashEmbedding(),
        agent_llm=scripted.llm,
        nest_transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    body = request_body()
    body["history"] = [
        {
            "role": "assistant",
            "content": "Preparé el borrador.",
            "activity": {"proposal": {"status": "confirmed", "result": {"id": "c-9"}}},
        }
    ]
    with TestClient(app) as client:
        assert client_post(client, body).status_code == 200

    sent = "\n".join(message.content or "" for message in scripted.messages[0])
    assert "status: confirmed" in sent
    assert "id: c-9" in sent


def test_run_accepts_the_project_sheet_and_bounds_its_size(
    disabled: TestClient,
) -> None:
    body = request_body()
    body["project"] = {"project": {"name": "Tienda"}, "sheets": []}
    assert client_post(disabled, body).status_code == 503
    body["project"] = {"notes": "x" * 140_000}
    assert client_post(disabled, body).status_code == 400


def test_the_run_starts_with_related_knowledge_from_qdrant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    organization, project = str(uuid4()), str(uuid4())
    monkeypatch.setattr(
        "ktsu_ai.bootstrap.app.create_client",
        lambda config: AsyncQdrantClient(location=":memory:"),
    )
    config = configuration_for(UNREACHABLE_QDRANT)
    config.nest_agent_base_url = HttpUrl("http://nest.test")
    scripted = ScriptedResponses(ChatMessage(role="assistant", content="Hecho."))
    app = create_app(
        config,
        WordHashEmbedding(),
        agent_llm=scripted.llm,
        nest_transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    source = (
        f"/v1/knowledge/organizations/{organization}/projects/{project}"
        f"/sources/catalog/{project}"
    )
    document = {
        "documentId": "SKU-77",
        "text": "Producto SKU-77 zapatillas rojas sin imagen en el feed",
        "metadata": {},
    }
    body = request_body()
    body["scope"] = {"organizationId": organization, "projectIds": [project]}
    body["message"] = "¿Qué zapatillas rojas no tienen imagen?"
    with TestClient(app) as client:
        indexed = client.put(source, headers=AUTHORIZED, json={"documents": [document]})
        assert indexed.status_code == 200
        assert client_post(client, body).status_code == 200

    system = scripted.messages[0][0].content or ""
    assert "Conocimiento del proyecto relacionado" in system
    assert "SKU-77" in system
