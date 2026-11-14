"""Composición HTTP: middleware, errores y las rutas de cada feature.

Cada feature recibe solo su puerto de entrada (`ApiServices`); quién lo
implementa lo decide `bootstrap`.
"""

from dataclasses import dataclass

from fastapi import FastAPI

from ktsu_ai.application.agent_ports.in_agent_use_case import IAgentUseCase
from ktsu_ai.application.health_ports.in_health_use_case import IHealthUseCase
from ktsu_ai.application.knowledge_ports.in_knowledge_use_case import (
    IKnowledgeUseCase,
)
from ktsu_ai.http.agent_http.routes import build_agent_router
from ktsu_ai.http.health_http.routes import build_health_router
from ktsu_ai.http.knowledge_http.routes import build_knowledge_router
from ktsu_ai.http.middleware.errors import install_error_handlers
from ktsu_ai.http.middleware.internal_auth import InternalAuth
from ktsu_ai.http.middleware.observability import observe_request


@dataclass(frozen=True)
class ApiServices:
    health: IHealthUseCase
    knowledge: IKnowledgeUseCase
    agent: IAgentUseCase | None = None


def mount_routes(app: FastAPI, services: ApiServices, auth: InternalAuth) -> None:
    app.middleware("http")(observe_request)
    install_error_handlers(app)
    app.include_router(build_health_router(services.health, auth))
    app.include_router(build_knowledge_router(services.knowledge, auth))
    app.include_router(build_agent_router(services.agent, auth))
