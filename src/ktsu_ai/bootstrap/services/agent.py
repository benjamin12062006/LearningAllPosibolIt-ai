"""Compone el agente con su modelo y la pasarela a Nest."""

import httpx
from llama_index.core.llms.function_calling import FunctionCallingLLM

from ktsu_ai.application.agent_application.agent_service import AgentService
from ktsu_ai.application.agent_ports.in_agent_use_case import IAgentUseCase
from ktsu_ai.infrastructure.agent_infrastructure.llamaindex_agent import LlamaIndexAgent
from ktsu_ai.infrastructure.agent_infrastructure.nest_operation_gateway import (
    NestOperationGateway,
)


def build_agent_service(
    llm: FunctionCallingLLM,
    client: httpx.AsyncClient,
) -> IAgentUseCase:
    return AgentService(LlamaIndexAgent(llm), NestOperationGateway(client))
