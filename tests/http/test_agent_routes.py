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
