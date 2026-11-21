"""Credenciales de Google en Vercel con federación OIDC (deploys, bitácora 07)."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth import exceptions, identity_pool
from google.auth.credentials import Credentials
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.llms.function_calling import FunctionCallingLLM
from pydantic import ValidationError
from qdrant_client import AsyncQdrantClient

from ktsu_ai.bootstrap.app import create_app_from_environment
from ktsu_ai.config.configuration import GoogleFederationConfiguration
from ktsu_ai.config.loader import load_configuration
from ktsu_ai.http.middleware.vercel_oidc import RememberVercelOidcToken
from ktsu_ai.infrastructure.google_credentials.vercel_federation import (
    LatestVercelOidcToken,
    create_vercel_federated_credentials,
)
from tests.support.scripted_llm import ScriptedResponses
from tests.support.word_hash_embedding import WordHashEmbedding

FEDERATION_VARIABLES = {
    "GCP_PROJECT_NUMBER": "758688457791",
    "GCP_WORKLOAD_IDENTITY_POOL_ID": "vercel",
    "GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID": "vercel",
    "GCP_SERVICE_ACCOUNT_EMAIL": "ktsu-ai@estadistica-forms-api.iam.gserviceaccount.com",
}


@pytest.fixture(autouse=True)
def minimal_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_SERVICE_TOKEN", "t" * 32)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "estadistica-forms-api")
    for name in FEDERATION_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_outside_vercel_google_uses_the_account_credentials() -> None:
    assert load_configuration(env_file=None).google_federation is None


def test_in_vercel_the_four_variables_describe_the_federation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in FEDERATION_VARIABLES.items():
        monkeypatch.setenv(name, value)

    federation = load_configuration(env_file=None).google_federation

    assert federation == GoogleFederationConfiguration(
        project_number="758688457791",
        pool_id="vercel",
        provider_id="vercel",
        service_account_email="ktsu-ai@estadistica-forms-api.iam.gserviceaccount.com",
    )


def test_a_half_configured_federation_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GCP_PROJECT_NUMBER", "758688457791")

    with pytest.raises(ValidationError):
        load_configuration(env_file=None)


def test_credentials_exchange_the_token_for_the_service_account() -> None:
    config = GoogleFederationConfiguration(**_federation_fields())

    credentials = create_vercel_federated_credentials(config, LatestVercelOidcToken())

    assert credentials.info["audience"] == (
        "//iam.googleapis.com/projects/758688457791/locations/global"
        "/workloadIdentityPools/vercel/providers/vercel"
    )
    assert credentials.service_account_email == (
        "ktsu-ai@estadistica-forms-api.iam.gserviceaccount.com"
    )


def test_without_any_request_there_is_no_token_to_exchange() -> None:
    with pytest.raises(exceptions.RefreshError):
        LatestVercelOidcToken().get_subject_token(None, None)  # type: ignore[arg-type]


def test_the_latest_request_token_is_the_one_exchanged() -> None:
    token = LatestVercelOidcToken()
    app = FastAPI()
    app.add_middleware(RememberVercelOidcToken, remember=token.remember)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    with TestClient(app) as client:
        client.get("/health", headers={"x-vercel-oidc-token": "first"})
        client.get("/health", headers={"x-vercel-oidc-token": "second"})
        client.get("/health")

    assert token.get_subject_token(None, None) == "second"  # type: ignore[arg-type]


def test_in_vercel_gemini_and_embeddings_use_the_federated_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Lejos del `.env` real del repositorio, que activa Gemini de verdad.
    monkeypatch.chdir(tmp_path)
    embedder = WordHashEmbedding()
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", str(embedder.dimensions))
    monkeypatch.setenv("NEST_AGENT_BASE_URL", "http://nest.test")
    monkeypatch.setenv("CHAT_MODEL", "m-prueba")
    for name, value in FEDERATION_VARIABLES.items():
        monkeypatch.setenv(name, value)
    received: dict[str, Credentials | None] = {}

    def gemini(config: object, credentials: Credentials | None) -> FunctionCallingLLM:
        received["gemini"] = credentials
        return ScriptedResponses(ChatMessage(role="assistant", content="Hola.")).llm

    def embedding(config: object, credentials: Credentials | None) -> WordHashEmbedding:
        received["embedding"] = credentials
        return embedder

    monkeypatch.setattr("ktsu_ai.bootstrap.app.create_gemini_chat_model", gemini)
    monkeypatch.setattr("ktsu_ai.bootstrap.app.create_google_embedding", embedding)
    monkeypatch.setattr(
        "ktsu_ai.bootstrap.app.create_client",
        lambda config: AsyncQdrantClient(location=":memory:"),
    )

    create_app_from_environment()

    assert isinstance(received["gemini"], identity_pool.Credentials)
    assert received["embedding"] is received["gemini"]


def _federation_fields() -> dict[str, str]:
    return {
        "project_number": FEDERATION_VARIABLES["GCP_PROJECT_NUMBER"],
        "pool_id": FEDERATION_VARIABLES["GCP_WORKLOAD_IDENTITY_POOL_ID"],
        "provider_id": FEDERATION_VARIABLES["GCP_WORKLOAD_IDENTITY_POOL_PROVIDER_ID"],
        "service_account_email": FEDERATION_VARIABLES["GCP_SERVICE_ACCOUNT_EMAIL"],
    }
