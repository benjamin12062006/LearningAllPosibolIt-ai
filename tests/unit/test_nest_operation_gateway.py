"""Qué llega al modelo cuando Nest rechaza una operación."""

import asyncio

import httpx
import pytest

from ktsu_ai.application.agent_ports.out_operation_gateway import OperationFailedError
from ktsu_ai.domain.access.access_scope import AccessScope
from ktsu_ai.domain.agent.agent_run import JsonObject, RunIdentity
from ktsu_ai.infrastructure.agent_infrastructure.nest_operation_gateway import (
    UNAVAILABLE,
    NestOperationGateway,
)

IDENTITY = RunIdentity("run-1", AccessScope("org", frozenset({"p"})), "secret")
TOO_LARGE: JsonObject = {
    "code": "AGENT_RESULT_TOO_LARGE",
    "message": {
        "es": "El resultado es demasiado grande. Pide menos filas.",
        "en": "The result is too large. Ask for fewer rows.",
    },
}


def failure_for(status: int, body: JsonObject | None) -> OperationFailedError:
    def nest(request: httpx.Request) -> httpx.Response:
        if body is None:
            return httpx.Response(status, content=b"no es json")
        return httpx.Response(status, json=body)

    client = httpx.AsyncClient(
        base_url="http://nest.test", transport=httpx.MockTransport(nest)
    )
    gateway = NestOperationGateway(client)
    with pytest.raises(OperationFailedError) as raised:
        asyncio.run(gateway.execute(IDENTITY, "query_rows", {}))
    return raised.value


@pytest.mark.parametrize("status", [400, 403, 404, 409, 413, 422, 429])
def test_every_public_rejection_reaches_the_model_with_its_code(status: int) -> None:
    error = failure_for(status, TOO_LARGE)

    assert str(error) == "El resultado es demasiado grande. Pide menos filas."
    assert error.for_model("es") == (
        "AGENT_RESULT_TOO_LARGE: El resultado es demasiado grande. Pide menos filas."
    )
    assert error.for_model("en") == (
        "AGENT_RESULT_TOO_LARGE: The result is too large. Ask for fewer rows."
    )


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (401, TOO_LARGE),
        (500, TOO_LARGE),
        (503, TOO_LARGE),
        (422, None),
        (422, {"code": "X"}),
        (422, {"code": "X", "message": {"es": "  "}}),
    ],
)
def test_credential_server_and_unreadable_failures_stay_generic(
    status: int, body: JsonObject | None
) -> None:
    error = failure_for(status, body)

    assert error.for_model("es") == UNAVAILABLE
    assert error.code is None
