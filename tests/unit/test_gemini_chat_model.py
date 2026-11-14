"""Gemini como modelo del agente, sin llamar a Google (plan 03 del agente, G-E1)."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.genai import types
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.llms.function_calling import FunctionCallingLLM
from qdrant_client import AsyncQdrantClient

from ktsu_ai.bootstrap.app import create_app_from_environment
from ktsu_ai.config.configuration import ChatModelConfiguration
from ktsu_ai.domain.agent.agent_run import AgentOperation, OperationLevel
from ktsu_ai.infrastructure.agent_infrastructure.gemini_chat_model import (
    GEMINI_CONTEXT_WINDOW,
    CatalogSchemaGemini,
    create_gemini_chat_model,
)
from ktsu_ai.infrastructure.agent_infrastructure.llamaindex_agent import _build_tools
from tests.http.test_agent_routes import request_body
from tests.support.scripted_llm import ScriptedResponses
from tests.support.word_hash_embedding import WordHashEmbedding

TOKEN = "t" * 32
CHAT = ChatModelConfiguration(
    model="gemini-3.5-flash-lite",
    location="global",
    thinking_level="MEDIUM",
    max_output_tokens=4_096,
    timeout_seconds=60,
    google_cloud_project="proyecto-de-prueba",
)
# Palabras clave que el `Schema` de Google rechaza o que el conector quitaba.
PRICE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rowIds": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "uniqueItems": True,
        },
        "percent": {"type": "string", "pattern": "^[0-9]+(\\.[0-9]+)?$"},
    },
    "required": ["rowIds", "percent"],
    "additionalProperties": False,
}
PRICE_OPERATION = AgentOperation(
    "propose_price_increase",
    "Prepara un cambio de precio sobre las filas indicadas.",
    PRICE_SCHEMA,
    OperationLevel.WRITE,
)


@pytest.fixture
def no_google_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Crear el modelo no debe preguntar nada a Google (ficha 03, E2)."""

    def refuse(*args: object, **kwargs: object) -> None:
        pytest.fail("El modelo llamó a Google al crearse.")

    monkeypatch.setattr("google.genai.models.Models.get", refuse)


@pytest.mark.usefixtures("no_google_calls")
def test_creates_gemini_without_calling_google() -> None:
    llm = create_gemini_chat_model(CHAT, AnonymousCredentials())

    assert isinstance(llm, CatalogSchemaGemini)
    assert llm.metadata.model_name == "gemini-3.5-flash-lite"
    assert llm.metadata.context_window == GEMINI_CONTEXT_WINDOW
    assert llm.metadata.num_output == 4_096
    assert llm.metadata.is_function_calling_model


@pytest.mark.usefixtures("no_google_calls")
def test_generation_uses_the_configured_reasoning_and_output_limit() -> None:
    llm = create_gemini_chat_model(
        CHAT.model_copy(update={"thinking_level": "HIGH", "max_output_tokens": 512}),
        AnonymousCredentials(),
    )

    config = llm._generation_config  # el conector la guarda como diccionario
    assert config["max_output_tokens"] == 512
    assert config["thinking_config"]["thinking_level"] == types.ThinkingLevel.HIGH


@pytest.mark.usefixtures("no_google_calls")
def test_declares_each_tool_with_the_complete_nest_schema() -> None:
    llm = create_gemini_chat_model(CHAT, AnonymousCredentials())
    tools = _build_tools((PRICE_OPERATION,), toolbox=_UnusedToolbox())

    params = llm._prepare_chat_with_tools(tools, user_msg="Sube un 5 %")

    declarations = {
        declaration.name: declaration
        for declaration in params["tools"][0].function_declarations
    }
    price = declarations["propose_price_increase"]
    assert price.parameters_json_schema == PRICE_SCHEMA
    assert price.parameters is None
    assert price.description == PRICE_OPERATION.description
    assert set(declarations) == {
        "propose_price_increase",
        "search_knowledge",
        "ask_for_clarification",
    }
    calling = params["tool_config"].function_calling_config
    assert calling.mode == types.FunctionCallingConfigMode.AUTO
    assert calling.allowed_function_names is None
    assert params["messages"][-1].content == "Sube un 5 %"


@pytest.mark.usefixtures("no_google_calls")
@pytest.mark.parametrize(
    ("options", "allowed"),
    [
        (
            {"tool_required": True},
            ["propose_price_increase", "search_knowledge", "ask_for_clarification"],
        ),
        ({"tool_choice": "search_knowledge"}, ["search_knowledge"]),
    ],
)
def test_a_required_tool_keeps_the_offered_names(
    options: dict[str, Any], allowed: list[str]
) -> None:
    llm = create_gemini_chat_model(CHAT, AnonymousCredentials())
    tools = _build_tools((PRICE_OPERATION,), toolbox=_UnusedToolbox())

    params = llm._prepare_chat_with_tools(tools, user_msg="hola", **options)

    calling = params["tool_config"].function_calling_config
    assert calling.mode == types.FunctionCallingConfigMode.ANY
    assert calling.allowed_function_names == allowed


def test_the_agent_uses_gemini_when_chat_model_is_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created = _start_from_environment(monkeypatch, tmp_path, chat_model="m-prueba")

    with TestClient(create_app_from_environment()) as client:
        response = client.post(
            "/v1/agent/runs",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json=request_body(),
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "Hola."
    assert [config.model for config in created] == ["m-prueba"]
    assert created[0].location == "global"
    assert created[0].google_cloud_project == "proyecto-de-prueba"


def test_without_chat_model_the_agent_stays_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    created = _start_from_environment(monkeypatch, tmp_path, chat_model="")

    with TestClient(create_app_from_environment()) as client:
        response = client.post(
            "/v1/agent/runs",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json=request_body(),
        )

    assert response.status_code == 503
    assert response.json()["code"] == "AGENT_UNAVAILABLE"
    assert created == []


def _start_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, chat_model: str
) -> list[ChatModelConfiguration]:
    """Arranque desde el entorno con Qdrant en memoria y sin Google."""
    # Lejos del `.env` real del repositorio, que activa Gemini de verdad.
    monkeypatch.chdir(tmp_path)
    embedder = WordHashEmbedding()
    for name, value in {
        "AI_SERVICE_TOKEN": TOKEN,
        "GOOGLE_CLOUD_PROJECT": "proyecto-de-prueba",
        "EMBEDDING_DIMENSIONS": str(embedder.dimensions),
        "NEST_AGENT_BASE_URL": "http://nest.test",
        "CHAT_MODEL": chat_model,
    }.items():
        monkeypatch.setenv(name, value)

    created: list[ChatModelConfiguration] = []

    def scripted_gemini(config: ChatModelConfiguration) -> FunctionCallingLLM:
        created.append(config)
        return ScriptedResponses(ChatMessage(role="assistant", content="Hola.")).llm

    monkeypatch.setattr(
        "ktsu_ai.bootstrap.app.create_gemini_chat_model", scripted_gemini
    )
    monkeypatch.setattr(
        "ktsu_ai.bootstrap.app.create_google_embedding", lambda config: embedder
    )
    monkeypatch.setattr(
        "ktsu_ai.bootstrap.app.create_client",
        lambda config: AsyncQdrantClient(location=":memory:"),
    )
    return created


class _UnusedToolbox:
    """Declarar herramientas no las ejecuta: nadie debe llamar a la caja."""

    async def invoke(self, name: str, arguments: object) -> None:
        pytest.fail("Declarar una herramienta no debe ejecutarla.")
