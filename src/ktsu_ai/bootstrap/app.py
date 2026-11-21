"""Composición del servicio: configuración → recursos → servicios → HTTP.

Es el único sitio que conoce a la vez la infraestructura y las rutas. `main` es
el arranque real (`uv run ktsu-ai`); `make dev` usa `create_app_from_environment`.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.llms.function_calling import FunctionCallingLLM

from ktsu_ai.bootstrap.resources import qdrant
from ktsu_ai.bootstrap.services.agent import build_agent_service
from ktsu_ai.bootstrap.services.health import build_health_service
from ktsu_ai.bootstrap.services.knowledge import build_knowledge_service
from ktsu_ai.config.configuration import Configuration
from ktsu_ai.config.loader import load_configuration
from ktsu_ai.http.http_server import serve
from ktsu_ai.http.middleware.internal_auth import InternalAuth
from ktsu_ai.http.middleware.vercel_oidc import RememberVercelOidcToken
from ktsu_ai.http.routes import ApiServices, mount_routes
from ktsu_ai.infrastructure.agent_infrastructure.gemini_chat_model import (
    create_gemini_chat_model,
)
from ktsu_ai.infrastructure.database.qdrant.connection import create_client
from ktsu_ai.infrastructure.embeddings.google_embedding import create_google_embedding
from ktsu_ai.infrastructure.google_credentials.vercel_federation import (
    LatestVercelOidcToken,
    create_vercel_federated_credentials,
)


def create_app(
    configuration: Configuration,
    embedder: BaseEmbedding | None = None,
    *,
    agent_llm: FunctionCallingLLM | None = None,
    nest_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Las pruebas inyectan embeddings, modelo de chat y transporte a Nest."""
    nest_client = None
    if agent_llm is not None:
        if configuration.nest_agent_base_url is None:
            raise ValueError("El agente requiere NEST_AGENT_BASE_URL.")
        nest_client = httpx.AsyncClient(
            base_url=str(configuration.nest_agent_base_url),
            transport=nest_transport,
            trust_env=False,
        )

    # Crear los clientes no conecta; la primera comprobación es al arrancar.
    qdrant_client = create_client(configuration.qdrant)
    embedder = embedder or create_google_embedding(configuration.embedding)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            await qdrant.report_availability(qdrant_client)
            yield
        finally:
            try:
                await qdrant_client.close()
            finally:
                if nest_client is not None:
                    await nest_client.aclose()

    # Sin documentación pública: el servicio es interno y solo lo llama Nest.
    app = FastAPI(
        title="KTSU AI",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    knowledge = build_knowledge_service(qdrant_client, embedder, configuration)
    agent = None
    if agent_llm is not None and nest_client is not None:
        agent = build_agent_service(agent_llm, nest_client)
    services = ApiServices(
        health=build_health_service(qdrant_client),
        knowledge=knowledge,
        agent=agent,
    )
    mount_routes(app, services, InternalAuth(configuration.auth.service_token))
    return app


def create_app_from_environment() -> FastAPI:
    """Para `uvicorn --factory` (recarga en desarrollo) y para `main`."""
    configuration = load_configuration()
    _configure_logging(configuration)
    return _create_configured_app(configuration)


def main() -> None:
    configuration = load_configuration()
    _configure_logging(configuration)
    serve(_create_configured_app(configuration), configuration.server)


def _create_configured_app(configuration: Configuration) -> FastAPI:
    """Con `CHAT_MODEL`, el agente usa Gemini; sin él, queda desactivado (503).

    En Vercel (`GCP_PROJECT_NUMBER`), Google se usa con la federación OIDC; en
    local y en GKE, con las credenciales de la cuenta (ADC).
    """
    vercel_token = None
    credentials = None
    if configuration.google_federation is not None:
        vercel_token = LatestVercelOidcToken()
        credentials = create_vercel_federated_credentials(
            configuration.google_federation, vercel_token
        )

    agent_llm = None
    if configuration.chat is not None:
        agent_llm = create_gemini_chat_model(configuration.chat, credentials)
    app = create_app(
        configuration,
        create_google_embedding(configuration.embedding, credentials),
        agent_llm=agent_llm,
    )

    if vercel_token is not None:
        app.add_middleware(RememberVercelOidcToken, remember=vercel_token.remember)
    return app


def _configure_logging(configuration: Configuration) -> None:
    logging.basicConfig(
        level=configuration.server.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # `httpx` deja una línea por cada llamada a Qdrant; la nuestra por petición basta.
    logging.getLogger("httpx").setLevel(logging.WARNING)
