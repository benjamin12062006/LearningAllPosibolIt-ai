"""Rutas de salud con el middleware real y un caso de uso simulado."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from ktsu_ai.application.health_application.dto_output_service_health_output import (
    DependencyStatusOutput,
    ServiceHealthOutput,
)
from ktsu_ai.http.middleware.internal_auth import InternalAuth
from ktsu_ai.http.routes import ApiServices, mount_routes

TOKEN = "token-de-prueba-con-32-caracteres!"
AUTHORIZED = {"Authorization": f"Bearer {TOKEN}"}


class FakeHealth:
    def __init__(self, ready: bool) -> None:
        self.ready = ready

    async def check_health(self) -> ServiceHealthOutput:
        status = "available" if self.ready else "unavailable"
        version = "1.19.1" if self.ready else None
        return ServiceHealthOutput(
            ready=self.ready,
            dependencies=(DependencyStatusOutput("qdrant", status, version),),
        )


def client_with(health: FakeHealth) -> TestClient:
    # Estas pruebas no tocan conocimiento: un objeto vacío basta para montar sus rutas.
    services = ApiServices(health=health, knowledge=object())  # type: ignore[arg-type]
    app = FastAPI()
    mount_routes(app, services, InternalAuth(SecretStr(TOKEN)))
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client() -> TestClient:
    return client_with(FakeHealth(ready=True))


def test_liveness_needs_no_token(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_reports_qdrant(client: TestClient) -> None:
    response = client.get("/v1/health", headers=AUTHORIZED)

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "dependencies": [
            {"name": "qdrant", "status": "available", "version": "1.19.1"}
        ],
    }


def test_readiness_is_503_when_a_dependency_is_down() -> None:
    response = client_with(FakeHealth(ready=False)).get(
        "/v1/health", headers=AUTHORIZED
    )

    assert response.status_code == 503
    assert response.json()["dependencies"][0]["status"] == "unavailable"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer otro-token-que-no-es-el-del-servicio!!"},
        {"Authorization": f"Basic {TOKEN}"},
        {"Authorization": TOKEN},
        {"Authorization": f"Bearer {TOKEN}x"},
    ],
    ids=["sin cabecera", "otro token", "otro esquema", "sin Bearer", "token más largo"],
)
def test_private_routes_need_the_service_token(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.get("/v1/health", headers=headers)

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "AUTH_SERVICE_TOKEN_INVALID"
    assert body["message"]["es"]
    assert body["message"]["en"]
    assert body["requestId"] == response.headers["X-Request-Id"]


def test_keeps_a_valid_request_id_from_nest(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-Id": "nest-req-12345"})

    assert response.headers["X-Request-Id"] == "nest-req-12345"


def test_replaces_an_unsafe_request_id(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-Id": "corto"})

    assert response.headers["X-Request-Id"] != "corto"
    assert len(response.headers["X-Request-Id"]) == 36


def test_unknown_routes_use_the_public_error_body(client: TestClient) -> None:
    response = client.get("/v1/no-existe", headers=AUTHORIZED)

    assert response.status_code == 404
    assert response.json()["code"] == "ROUTE_NOT_FOUND"


def test_logs_one_line_per_request_without_the_token(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="ktsu_ai.http"):
        client.get("/v1/health?secreto=1", headers=AUTHORIZED)

    lines = [record.getMessage() for record in caplog.records]
    assert len(lines) == 1
    assert lines[0].startswith("HTTP GET /v1/health 200 ")
    assert TOKEN not in lines[0]
    assert "secreto" not in lines[0]
