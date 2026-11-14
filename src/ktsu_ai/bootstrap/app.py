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
from ktsu_ai.http.routes import ApiServices, mount_routes
from ktsu_ai.infrastructure.agent_infrastructure.gemini_chat_model import (
    create_gemini_chat_model,
)
from ktsu_ai.infrastructure.database.qdrant.connection import create_client
from ktsu_ai.infrastructure.embeddings.google_embedding import create_google_embedding


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
        agent = build_agent_service(
            agent_llm, nest_client, knowledge, qdrant_client, embedder, configuration
        )
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
    """Con `CHAT_MODEL`, el agente usa Gemini; sin él, queda desactivado (503)."""
    if configuration.chat is None:
        return create_app(configuration)
    return create_app(
        configuration, agent_llm=create_gemini_chat_model(configuration.chat)
    )


def _configure_logging(configuration: Configuration) -> None:
    logging.basicConfig(
        level=configuration.server.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # `httpx` deja una línea por cada llamada a Qdrant; la nuestra por petición basta.
    logging.getLogger("httpx").setLevel(logging.WARNING)
