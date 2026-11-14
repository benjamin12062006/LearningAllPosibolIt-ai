"""Entrada autenticada del agente, llamada únicamente por Nest."""

from fastapi import APIRouter, Depends

from ktsu_ai.application.agent_ports.in_agent_use_case import IAgentUseCase
from ktsu_ai.common.error import AppError, ErrorCode
from ktsu_ai.domain.agent.agent_outcome import AgentOutcome
from ktsu_ai.http.agent_http.agent_dto import AgentRunRequest
from ktsu_ai.http.middleware.internal_auth import InternalAuth


def build_agent_router(agent: IAgentUseCase | None, auth: InternalAuth) -> APIRouter:
    router = APIRouter(tags=["agent"], dependencies=[Depends(auth)])

    @router.post("/v1/agent/runs")
    async def run_agent(body: AgentRunRequest) -> AgentOutcome:
        try:
            run = body.to_domain()
        except ValueError:
            raise AppError(ErrorCode.VALIDATION_FAILED) from None
        if agent is None:
            raise AppError(ErrorCode.AGENT_UNAVAILABLE)
        return await agent.run(run)

    return router
